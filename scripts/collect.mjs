import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const dataPath = path.join(root, 'data', 'rankings.json');

const CATEGORIES = {
  free_today: { label: '무료 베스트', section: 'today' },
  paid_today: { label: '유료 베스트', section: 'plsa.eachtoday' },
  exclusive_today: { label: '선독점 베스트', section: 'plsa.exclusive-eachtoday' },
  favorites: { label: '선호작 베스트', section: 'prefer' },
  bestseller: { label: '베스트셀러', section: 'plsa.bestseller' }
};

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
  return value.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (_, entity) => {
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
    .replace(/^\s*(NEW|완결|독점)\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function extractTitles(html) {
  const titles = [];
  const seen = new Set();
  const push = raw => {
    const title = cleanTitle(raw);
    if (!title || title.length < 2 || title.length > 100 || seen.has(title)) return;
    seen.add(title);
    titles.push(title);
  };

  const altPatterns = [
    /<img\b[^>]*\balt=["']([^"']+?)의\s*표지["'][^>]*>/gi,
    /<img\b[^>]*\balt=["']표지\s*[:：]\s*([^"']+?)["'][^>]*>/gi
  ];
  for (const pattern of altPatterns) {
    for (const match of html.matchAll(pattern)) push(match[1]);
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

async function fetchPage(section, page, attempt = 1) {
  const url = new URL('https://mm.munpia.com/');
  url.searchParams.set('action', 'list');
  url.searchParams.set('menu', 'best');
  url.searchParams.set('section', section);
  url.searchParams.set('page', String(page));

  const response = await fetch(url, {
    headers: {
      'user-agent': 'Mozilla/5.0 (compatible; MunpiaTitleArchive/1.0; +https://github.com/MikeShin0822/munpia-ranking)',
      'accept-language': 'ko-KR,ko;q=0.9,en;q=0.6',
      accept: 'text/html,application/xhtml+xml'
    },
    signal: AbortSignal.timeout(25000)
  });

  if (!response.ok) {
    if (attempt < 3 && [429, 500, 502, 503, 504].includes(response.status)) {
      await new Promise(resolve => setTimeout(resolve, attempt * 2000));
      return fetchPage(section, page, attempt + 1);
    }
    throw new Error(`${url} 응답 ${response.status}`);
  }
  return { url: url.toString(), html: await response.text() };
}

async function collectCategory(config) {
  const titles = [];
  const seen = new Set();
  let source = '';

  for (let page = 1; page <= 4 && titles.length < 30; page += 1) {
    const result = await fetchPage(config.section, page);
    source ||= result.url;
    const pageTitles = extractTitles(result.html);
    if (!pageTitles.length && page === 1) throw new Error('제목을 찾지 못했습니다. 페이지 구조를 확인하세요.');
    for (const title of pageTitles) {
      if (!seen.has(title)) {
        seen.add(title);
        titles.push(title);
      }
      if (titles.length === 30) break;
    }
  }

  return {
    label: config.label,
    collectedAt: kstIso(),
    status: titles.length >= 30 ? 'complete' : 'partial',
    source,
    titles: titles.slice(0, 30)
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

  const results = await Promise.allSettled(Object.entries(CATEGORIES).map(async ([key, config]) => {
    const ranking = await collectCategory(config);
    return [key, ranking];
  }));

  const messages = [];
  results.forEach((result, index) => {
    const key = Object.keys(CATEGORIES)[index];
    if (result.status === 'fulfilled') {
      const [resolvedKey, ranking] = result.value;
      snapshot.rankings[resolvedKey] = ranking;
      messages.push(`${CATEGORIES[resolvedKey].label} ${ranking.titles.length}개`);
    } else {
      messages.push(`${CATEGORIES[key].label} 실패: ${result.reason.message}`);
      console.error(`[${key}]`, result.reason);
    }
  });

  data.snapshots.sort((a, b) => a.date.localeCompare(b.date));
  data.updatedAt = kstIso();
  data.collectionLog ??= [];
  data.collectionLog.push({ date, message: messages.join(' · ') });
  data.collectionLog = data.collectionLog.slice(-90);
  await fs.writeFile(dataPath, `${JSON.stringify(data, null, 2)}\n`);

  const successCount = results.filter(result => result.status === 'fulfilled').length;
  if (!successCount) process.exitCode = 1;
  console.log(messages.join('\n'));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
