export const CATEGORY_META = {
  free_today: { label: '무료 베스트', short: '무료', tone: 'violet' },
  paid_today: { label: '유료 베스트', short: '유료', tone: 'amber' },
  exclusive_today: { label: '선독점 베스트', short: '선독점', tone: 'blue' },
  favorites: { label: '선호작 베스트', short: '선호작', tone: 'green' },
  bestseller: { label: '베스트셀러', short: '베스트셀러', tone: 'red' }
};

const STOP_WORDS = new Set([
  '가', '이', '은', '는', '을', '를', '에', '의', '와', '과', '도', '로', '으로',
  '내', '나', '후', '한', '번', '더', '좀', '너무', '잘', '안', '못', '다', '그',
  '됨', '함', '했다', '되었다', '되다', '합니다', '에서', '에게', '들이', '들의',
  '그리고', '이번', '혼자', '자꾸', '보니', '했더니', '인데', '이라', '이라서'
]);

const IMPORTANT_SINGLE = new Set(['탑', '신', '뇌', '별', '돈']);
const PARTICLES = ['에게서', '한테서', '으로부터', '에서', '에게', '한테', '까지', '부터', '처럼', '보다', '으로', '로', '의', '은', '는', '이', '가', '을', '를', '와', '과', '도', '만', '에'];

const CONCEPT_RULES = [
  [/^천재/i, '천재'], [/천재/, '천재'],
  [/마법사/, '마법사'], [/흑마법사/, '마법사'], [/대마법사/, '마법사'],
  [/집착/, '집착'], [/회귀/, '회귀'], [/빙의/, '빙의'], [/각성/, '각성'],
  [/재벌/, '재벌'], [/아포칼립스/, '아포칼립스'], [/무림/, '무림'], [/선협/, '선협'],
  [/무당/, '무당'], [/주술사/, '주술사'], [/신점/, '신점'],
  [/국정원/, '국정원'], [/CIA/i, 'CIA'], [/미국/, '미국'],
  [/독재/, '독재'], [/제국주의/, '제국주의'], [/방구석/, '방구석'],
  [/착각/, '착각'], [/탑/, '탑'], [/축구/, '축구'], [/야구/, '야구'],
  [/감독/, '감독'], [/배우/, '배우'], [/회장/, '회장'], [/황제/, '황제']
];

function stripParticles(token) {
  let value = token;
  for (const particle of PARTICLES) {
    if (value.length > particle.length + 1 && value.endsWith(particle)) {
      value = value.slice(0, -particle.length);
      break;
    }
  }
  return value;
}

export function normalizeToken(raw) {
  let token = String(raw ?? '')
    .normalize('NFKC')
    .replace(/[\p{P}\p{S}]+/gu, '')
    .trim();

  if (!token) return '';
  token = stripParticles(token);

  for (const [rule, replacement] of CONCEPT_RULES) {
    if (rule.test(token)) return replacement;
  }

  if (/^\d+$/.test(token)) return '';
  if (token.length === 1 && !IMPORTANT_SINGLE.has(token)) return '';
  if (STOP_WORDS.has(token)) return '';
  return token;
}

export function tokenizeTitle(title) {
  const normalized = String(title ?? '').normalize('NFKC');
  const segmenter = typeof Intl !== 'undefined' && Intl.Segmenter
    ? new Intl.Segmenter('ko', { granularity: 'word' })
    : null;

  const rawTokens = segmenter
    ? [...segmenter.segment(normalized)].filter(part => part.isWordLike).map(part => part.segment)
    : normalized.split(/\s+/);

  const tokens = rawTokens.map(normalizeToken).filter(Boolean);
  const concepts = CONCEPT_RULES
    .filter(([rule]) => rule.test(normalized))
    .map(([, replacement]) => replacement);

  return [...new Set([...tokens, ...concepts])];
}

export function getAvailableDates(data) {
  return [...new Set((data.snapshots ?? []).map(snapshot => snapshot.date))].sort();
}

export function getDateRange(endDate, period) {
  const end = new Date(`${endDate}T12:00:00+09:00`);
  const days = period === 'month' ? 30 : period === 'week' ? 7 : 1;
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  const format = date => new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(date);
  return { startDate: format(start), endDate: format(end), days };
}

export function flattenEntries(data, { startDate, endDate, categories }) {
  const selected = new Set(categories);
  const entries = [];
  for (const snapshot of data.snapshots ?? []) {
    if (snapshot.date < startDate || snapshot.date > endDate) continue;
    for (const [category, ranking] of Object.entries(snapshot.rankings ?? {})) {
      if (!selected.has(category)) continue;
      (ranking.titles ?? []).forEach((title, index) => {
        entries.push({
          date: snapshot.date,
          category,
          title,
          rank: index + 1,
          status: ranking.status ?? 'complete'
        });
      });
    }
  }
  return entries;
}

export function analyzeKeywords(entries, { limit = 30 } = {}) {
  const stats = new Map();
  for (const entry of entries) {
    const keywords = tokenizeTitle(entry.title);
    for (const keyword of keywords) {
      const current = stats.get(keyword) ?? {
        keyword, count: 0, score: 0, rankSum: 0, bestRank: 999, titles: new Set()
      };
      current.count += 1;
      current.score += Math.max(1, 31 - entry.rank);
      current.rankSum += entry.rank;
      current.bestRank = Math.min(current.bestRank, entry.rank);
      current.titles.add(entry.title);
      stats.set(keyword, current);
    }
  }
  return [...stats.values()]
    .map(item => ({
      ...item,
      averageRank: item.rankSum / item.count,
      uniqueTitles: item.titles.size,
      titles: [...item.titles]
    }))
    .filter(item => item.count >= 2 || item.score >= 25)
    .sort((a, b) => b.score - a.score || b.count - a.count || a.averageRank - b.averageRank)
    .slice(0, limit);
}

export function keywordSummary(entries, keyword) {
  const query = String(keyword ?? '').trim().normalize('NFKC').toLocaleLowerCase('ko-KR');
  if (!query) return { keyword: '', count: 0, score: 0, averageRank: null, bestRank: null, byDate: [], matches: [] };

  const matches = entries.filter(entry => entry.title.normalize('NFKC').toLocaleLowerCase('ko-KR').includes(query));
  const byDateMap = new Map();
  let score = 0;
  let rankSum = 0;
  let bestRank = null;

  for (const entry of matches) {
    score += Math.max(1, 31 - entry.rank);
    rankSum += entry.rank;
    bestRank = bestRank === null ? entry.rank : Math.min(bestRank, entry.rank);
    byDateMap.set(entry.date, (byDateMap.get(entry.date) ?? 0) + 1);
  }

  const dates = [...new Set(entries.map(entry => entry.date))].sort();
  return {
    keyword,
    count: matches.length,
    score,
    averageRank: matches.length ? rankSum / matches.length : null,
    bestRank,
    byDate: dates.map(date => ({ date, count: byDateMap.get(date) ?? 0 })),
    matches
  };
}

export function findTopPhrases(entries, limit = 12) {
  const stats = new Map();
  for (const entry of entries) {
    const tokens = tokenizeTitle(entry.title);
    const phrases = [];
    for (let i = 0; i < tokens.length - 1; i += 1) {
      phrases.push(`${tokens[i]} ${tokens[i + 1]}`);
    }
    for (const phrase of new Set(phrases)) {
      const item = stats.get(phrase) ?? { phrase, count: 0, score: 0 };
      item.count += 1;
      item.score += Math.max(1, 31 - entry.rank);
      stats.set(phrase, item);
    }
  }
  return [...stats.values()]
    .filter(item => item.count >= 2)
    .sort((a, b) => b.score - a.score || b.count - a.count)
    .slice(0, limit);
}
