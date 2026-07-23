import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { analyzeKeywords, flattenEntries, getDateRange, keywordSummary, tokenizeTitle } from '../src/analytics.js';
import { extractTitles } from './collect.mjs';

const data = JSON.parse(await fs.readFile(new URL('../data/rankings.json', import.meta.url), 'utf8'));
const range = getDateRange('2026-07-23', 'day');
const entries = flattenEntries(data, {
  ...range,
  categories: ['free_today', 'paid_today', 'exclusive_today', 'favorites', 'bestseller']
});

assert.equal(entries.length, 130, '초기 제목 데이터는 130개여야 합니다.');
assert(tokenizeTitle('미국에서 천재 마법사가 되었다').includes('미국'));
assert(tokenizeTitle('미국에서 천재 마법사가 되었다').includes('천재'));
assert(tokenizeTitle('미국에서 천재 마법사가 되었다').includes('마법사'));

const america = keywordSummary(entries, '미국');
assert(america.count >= 1, '미국 키워드가 집계되어야 합니다.');
assert(america.score > 0, '순위 점수가 계산되어야 합니다.');

const keywords = analyzeKeywords(entries);
assert(keywords.length > 5, '반복 키워드 분석 결과가 있어야 합니다.');

const html = '<img src="cover.jpg" alt="첫 번째 작품의 표지"><img alt="두 번째 작품의 표지" src="cover2.jpg">';
assert.deepEqual(extractTitles(html), ['첫 번째 작품', '두 번째 작품']);

console.log('All tests passed.');
