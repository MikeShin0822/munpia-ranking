import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  CATEGORY_META,
  analyzeKeywords,
  flattenEntries,
  getDateRange,
  keywordSummary
} from '../src/analytics.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const dataPath = path.join(root, 'data', 'rankings.json');
const reportPath = path.join(root, 'data', 'latest-report.json');
const WATCH_KEYWORDS = ['미국', '집착', '천재', '마법사', '탑', '회귀', '빙의', '재벌', '아포칼립스', '무당', '신점', '착각'];

function rankMap(ranking) {
  return new Map((ranking?.titles ?? []).map((title, index) => [title, index + 1]));
}

function categoryChange(current, previous) {
  const currentMap = rankMap(current);
  const previousMap = rankMap(previous);
  const entered = [...currentMap.entries()]
    .filter(([title]) => !previousMap.has(title))
    .map(([title, rank]) => ({ title, rank }));
  const exited = [...previousMap.entries()]
    .filter(([title]) => !currentMap.has(title))
    .map(([title, previousRank]) => ({ title, previousRank }));
  const movers = [...currentMap.entries()]
    .filter(([title]) => previousMap.has(title))
    .map(([title, rank]) => ({ title, rank, previousRank: previousMap.get(title), change: previousMap.get(title) - rank }))
    .filter(item => item.change !== 0)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change) || a.rank - b.rank)
    .slice(0, 10);
  return { entered, exited, movers };
}

function periodReport(data, endDate, period) {
  const range = getDateRange(endDate, period);
  const categories = Object.keys(CATEGORY_META);
  const entries = flattenEntries(data, { ...range, categories });
  const keywords = analyzeKeywords(entries, { limit: 30 }).map(item => ({
    keyword: item.keyword,
    count: item.count,
    score: item.score,
    averageRank: Number(item.averageRank.toFixed(2)),
    bestRank: item.bestRank,
    uniqueTitles: item.uniqueTitles
  }));
  const watched = Object.fromEntries(WATCH_KEYWORDS.map(keyword => {
    const summary = keywordSummary(entries, keyword);
    return [keyword, {
      count: summary.count,
      score: summary.score,
      averageRank: summary.averageRank === null ? null : Number(summary.averageRank.toFixed(2)),
      bestRank: summary.bestRank
    }];
  }));
  return {
    startDate: range.startDate,
    endDate: range.endDate,
    titleEntries: entries.length,
    uniqueTitles: new Set(entries.map(entry => entry.title)).size,
    collectionDays: new Set(entries.map(entry => entry.date)).size,
    keywords,
    watched
  };
}

const data = JSON.parse(await fs.readFile(dataPath, 'utf8'));
const snapshots = [...(data.snapshots ?? [])].sort((a, b) => a.date.localeCompare(b.date));
const latest = snapshots.at(-1);
const previous = snapshots.at(-2) ?? null;
if (!latest) throw new Error('수집된 스냅샷이 없습니다.');

const categories = Object.fromEntries(Object.entries(CATEGORY_META).map(([key, meta]) => {
  const current = latest.rankings?.[key] ?? { titles: [], status: 'failed' };
  const prior = previous?.rankings?.[key] ?? { titles: [] };
  return [key, {
    label: meta.label,
    status: current.status ?? 'unknown',
    count: current.titles?.length ?? 0,
    collectedAt: current.collectedAt ?? null,
    collectionDate: current.collectionDate ?? null,
    source: current.source ?? null,
    error: current.error ?? null,
    top30: current.titles ?? [],
    changes: categoryChange(current, prior)
  }];
}));

const report = {
  generatedAt: data.updatedAt,
  date: latest.date,
  previousDate: previous?.date ?? null,
  categories,
  periods: {
    day: periodReport(data, latest.date, 'day'),
    week: periodReport(data, latest.date, 'week'),
    month: periodReport(data, latest.date, 'month')
  },
  collectionLog: (data.collectionLog ?? []).slice(-7)
};

await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(`Generated ${reportPath}`);
