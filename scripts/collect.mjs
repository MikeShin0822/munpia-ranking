import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const dataPath = path.join(root, 'data', 'rankings.json');

const CATEGORIES = {
  free_today: { label: '무료 베스트', ajaxSection: 'today' },
  paid_today: { label: '유료 베스트', ajaxSection: 'plsa.eachtoday' },
  exclusive_today: {
    label: '선독점 베스트',
    desktopPath: 'plsa.exclusive-eachtoday'
  },
  favorites: { label: '선호작 베스트', ajaxSection: 'prefer' },
  bestseller: { label: '베스트셀러', ajaxSection: 'plsa.bestseller' }
};

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function kstDate(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(now);
}

function kstIso(now = new Date()) {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }).format(now).replace(' ', 'T');
  return `${parts}+09:00`;
}

function decodeHtml(value) {
  const entities = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' '
  };
  return String(value).replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (_, entity) => {
    if (entity[0] === '#') {
      const hex = entity[1].toLowerCase() === 'x';
      return String.fromCodePoint(parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10));
    }
    return entities[entity.toLowerCase()] ?? _;
  });
}

function cleanTitle(value) {
  return decodeHtml(value)
    .replace(/<[^>]+>/g, ' ')
    .replace(/^\s*(NEW|완결|독점|공모전)\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function pushUnique(target, seen, raw) {
  const title = cleanTitle(raw);
  if (!title || title.length < 2 || title.length > 100 || seen.has(title)) return;
  seen.add(title);
  target.push(title);
}

export function extractTitles(html) {
  const titles = [];
  const seen = new Set();
  const push = raw => pushUnique(titles, seen, raw);

  const patterns = [
    /<span\b[^>]*class=["'][^"']*\btitle-wrap\b[^"']*["'][^>]*>([\s\S]*?)<\/span>/gi,
    /<img\b[^>]*\balt=["']([^"']+?)의\s*표지["'][^>]*>/gi,
    /<img\b[^>]*\balt=["']표지\s*[:：]\s*([^"']+?)["'][^>]*>/gi
  ];

  for (const pattern of patterns) {
    for (const match of html.matchAll(pattern)) push(match[1]);
    if (titles.length >= 30) break;
  }

  if (titles.length < 5) {
    const linkPattern = /<a\b[^>]*href=["'][^"']*(?:novel|menu=novel|action=view)[^"']*["'][^>]*>([\s\S]*?)<\/a>/gi;
    for (const match of html.matchAll(linkPattern)) {
      const text = cleanTitle(match[1]);
      if (!/^(더보기|처음|이전|다음|마지막)$/.test(text)) push(text);
    }
  }

  return titles;
}

async function fetchWithRetry(url, { parse = 'text', attempt = 1 } = {}) {
  const response = await fetch(url, {
    headers: {
      'user-agent': 'Mozilla/5.0 (compatible; MunpiaTitleArchive/1.1; +https://github.com/MikeShin0822/munpia-ranking)',
      'accept-language': 'ko-KR,ko;q=0.9,en;q=0.6',
      accept: parse === 'json' ? 'application/json,text/plain,*/*' : 'text/html,application/xhtml+xml'
    },
    signal: AbortSignal.timeout(30000)
  });

  if (!response.ok) {
    if (attempt < 4 && [429, 500, 502, 503, 504].includes(response.status)) {
      const retryAfter = Number(response.headers.get('retry-after'));
      const waitMs = Number.isFinite(retryAfter) && retryAfter > 0
        ? retryAfter * 1000
        : Math.min(30000, 4000 * 2 ** (attempt - 1));
      await sleep(waitMs);
      return fetchWithRetry(url, { parse, attempt: attempt + 1 });
    }
    throw new Error(`${url} 응답 ${response.status}`);
  }

  if (parse === 'json') {
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`${url} JSON 해석 실패: ${text.slice(0, 120)}`);
    }
  }
  return response.text();
}

function ajaxUrl(section, page) {
  const url = new URL('https://mm.munpia.com/');
  url.searchParams.set('ajx', '1');
  url.searchParams.set('menu', 'best');
  url.searchParams.set('action', 'list');
  url.searchParams.set('section', section);
  url.searchParams.set('keyword', '');
  url.searchParams.set('page', String(page));
  return url;
}

async function collectAjaxCategory(config) {
  const titles = [];
  const seen = new Set();
  let source = '';
  let collectionDate = null;
  let error = null;

  for (let page = 1; page <= 3 && titles.length < 30; page += 1) {
    const url = ajaxUrl(config.ajaxSection, page);
    source ||= url.toString();
    try {
      const payload = await fetchWithRetry(url, { parse: 'json' });
      collectionDate ||= payload.get_date ?? null;
      const list = Array.isArray(payload.list) ? payload.list : [];
      if (!list.length) {
        error = page === 1 ? '첫 페이지에서 작품을 찾지 못했습니다.' : `${page}페이지가 비어 있습니다.`;
        break;
      }
      for (const entry of list) pushUnique(titles, seen, entry?.nvTitle ?? '');
      if (page >= Number(payload.last || page)) break;
    } catch (caught) {
      error = caught.message;
      break;
    }
    if (page < 3) await sleep(1800);
  }

  return { titles: titles.slice(0, 30), source, collectionDate, error };
}

async function collectDesktopCategory(config) {
  const url = `https://www.munpia.com/best/${config.desktopPath}`;
  const html = await fetchWithRetry(url);
  const titles = extractTitles(html).slice(0, 30);
  return {
    titles,
    source: url,
    collectionDate: null,
    error: titles.length ? null : '데스크톱 페이지에서 작품을 찾지 못했습니다.'
  };
}

async function collectCategory(config) {
  const result = config.ajaxSection
    ? await collectAjaxCategory(config)
    : await collectDesktopCategory(config);

  return {
    label: config.label,
    collectedAt: kstIso(),
    collectionDate: result.collectionDate,
    status: result.titles.length >= 30 ? 'complete' : 'partial',
    source: result.source,
    ...(result.error ? { error: result.error } : {}),
    titles: result.titles
  };
}

async function main() {
  const data = JSON.parse(await fs.readFile(dataPath, 'utf8'));
  const date = kstDate();
  let snapshot = data.snapshots.find(item => item.date === date);
  if (!snapshot) {
    snapshot = { date, rankings: {} };
    data.snapshots.push(snapshot);
  }

  const messages = [];
  let successCount = 0;
  for (const [key, config] of Object.entries(CATEGORIES)) {
    try {
      const ranking = await collectCategory(config);
      snapshot.rankings[key] = ranking;
      successCount += ranking.titles.length > 0 ? 1 : 0;
      const suffix = ranking.error ? ` (${ranking.error})` : '';
      messages.push(`${config.label} ${ranking.titles.length}개${suffix}`);
    } catch (error) {
      snapshot.rankings[key] = {
        label: config.label,
        collectedAt: kstIso(),
        status: 'failed',
        source: config.ajaxSection ? ajaxUrl(config.ajaxSection, 1).toString() : `https://www.munpia.com/best/${config.desktopPath}`,
        error: error.message,
        titles: []
      };
      messages.push(`${config.label} 실패: ${error.message}`);
      console.error(`[${key}]`, error);
    }
    await sleep(2500);
  }

  data.snapshots.sort((a, b) => a.date.localeCompare(b.date));
  data.updatedAt = kstIso();
  data.collectionLog ??= [];
  data.collectionLog.push({ date, message: messages.join(' · ') });
  data.collectionLog = data.collectionLog.slice(-90);
  await fs.writeFile(dataPath, `${JSON.stringify(data, null, 2)}\n`);

  if (!successCount) process.exitCode = 1;
  console.log(messages.join('\n'));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
