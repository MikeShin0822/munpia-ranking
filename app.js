import {
  CATEGORY_META,
  analyzeKeywords,
  findTopPhrases,
  flattenEntries,
  getAvailableDates,
  getDateRange,
  keywordSummary
} from './src/analytics.js';

const state = {
  data: null,
  activeView: 'titles',
  activeDate: '',
  activeCategory: 'free_today',
  titleQuery: '',
  period: 'day',
  insightCategories: new Set(Object.keys(CATEGORY_META)),
  keywordQuery: '미국'
};

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

function formatDate(date) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short'
  }).format(new Date(`${date}T12:00:00+09:00`));
}

async function loadData() {
  const response = await fetch('./data/rankings.json', { cache: 'no-store' });
  if (!response.ok) throw new Error(`데이터를 불러오지 못했습니다: ${response.status}`);
  state.data = await response.json();
  const dates = getAvailableDates(state.data);
  state.activeDate = dates.at(-1) ?? '';
}

function renderNav() {
  $$('.nav-button').forEach(button => {
    button.classList.toggle('active', button.dataset.view === state.activeView);
  });
  $('#titles-view').hidden = state.activeView !== 'titles';
  $('#insights-view').hidden = state.activeView !== 'insights';
}

function renderDateSelects() {
  const dates = getAvailableDates(state.data).reverse();
  const options = dates.map(date => `<option value="${date}">${formatDate(date)}</option>`).join('');
  $('#title-date').innerHTML = options;
  $('#insight-date').innerHTML = options;
  $('#title-date').value = state.activeDate;
  $('#insight-date').value = state.activeDate;
}

function currentSnapshot() {
  return state.data.snapshots.find(snapshot => snapshot.date === state.activeDate);
}

function renderCategoryTabs() {
  const rankings = currentSnapshot()?.rankings ?? {};
  $('#category-tabs').innerHTML = Object.entries(CATEGORY_META).map(([key, meta]) => {
    const count = rankings[key]?.titles?.length ?? 0;
    const status = rankings[key]?.status === 'partial' ? ' · 일부' : '';
    return `<button class="category-tab ${state.activeCategory === key ? 'active' : ''}" data-category="${key}">
      <span>${meta.label}</span><small>${count}개${status}</small>
    </button>`;
  }).join('');

  $$('#category-tabs .category-tab').forEach(button => {
    button.addEventListener('click', () => {
      state.activeCategory = button.dataset.category;
      renderTitles();
      renderCategoryTabs();
    });
  });
}

function renderTitles() {
  const ranking = currentSnapshot()?.rankings?.[state.activeCategory];
  const titles = ranking?.titles ?? [];
  const query = state.titleQuery.trim().toLocaleLowerCase('ko-KR');
  const filtered = titles
    .map((title, index) => ({ title, rank: index + 1 }))
    .filter(item => !query || item.title.toLocaleLowerCase('ko-KR').includes(query));

  $('#titles-heading').textContent = ranking?.label ?? CATEGORY_META[state.activeCategory].label;
  $('#titles-meta').textContent = ranking
    ? `${formatDate(state.activeDate)} · ${titles.length}개 제목${ranking.status === 'partial' ? ' · 현재 일부 수집' : ''}`
    : '수집된 데이터가 없습니다.';

  $('#title-list').innerHTML = filtered.length ? filtered.map(item => `
    <article class="title-row">
      <div class="rank ${item.rank <= 3 ? 'top' : ''}">${item.rank}</div>
      <div class="title-text">${escapeHtml(item.title)}</div>
      <button class="copy-button" data-title="${escapeHtml(item.title)}" aria-label="제목 복사">복사</button>
    </article>
  `).join('') : '<div class="empty-state">검색 조건에 맞는 제목이 없습니다.</div>';

  $$('#title-list .copy-button').forEach(button => {
    button.addEventListener('click', async () => {
      await navigator.clipboard.writeText(button.dataset.title);
      const original = button.textContent;
      button.textContent = '완료';
      setTimeout(() => { button.textContent = original; }, 900);
    });
  });
}

function renderInsightCategoryFilters() {
  $('#insight-categories').innerHTML = Object.entries(CATEGORY_META).map(([key, meta]) => `
    <label class="check-chip ${state.insightCategories.has(key) ? 'checked' : ''}">
      <input type="checkbox" value="${key}" ${state.insightCategories.has(key) ? 'checked' : ''}>
      <span>${meta.short}</span>
    </label>
  `).join('');

  $$('#insight-categories input').forEach(input => {
    input.addEventListener('change', () => {
      if (input.checked) state.insightCategories.add(input.value);
      else state.insightCategories.delete(input.value);
      if (!state.insightCategories.size) {
        state.insightCategories.add(input.value);
        input.checked = true;
      }
      renderInsights();
      renderInsightCategoryFilters();
    });
  });
}

function renderBars(items) {
  if (!items.length) return '<div class="empty-state">선택한 기간에 분석할 제목이 없습니다.</div>';
  const maxScore = Math.max(...items.map(item => item.score), 1);
  return items.slice(0, 15).map((item, index) => `
    <button class="bar-row" data-keyword="${escapeHtml(item.keyword)}">
      <span class="bar-rank">${index + 1}</span>
      <span class="bar-label">${escapeHtml(item.keyword)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${Math.max(4, item.score / maxScore * 100)}%"></span></span>
      <span class="bar-value"><b>${item.count}</b>회 <small>평균 ${item.averageRank.toFixed(1)}위</small></span>
    </button>
  `).join('');
}

function renderSparkline(points) {
  if (!points.length) return '';
  const width = 540;
  const height = 150;
  const padding = 18;
  const max = Math.max(1, ...points.map(point => point.count));
  const x = index => points.length === 1 ? width / 2 : padding + index * ((width - padding * 2) / (points.length - 1));
  const y = value => height - padding - (value / max) * (height - padding * 2);
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.count)}`).join(' ');
  const dots = points.map((point, index) => `<circle cx="${x(index)}" cy="${y(point.count)}" r="5"><title>${point.date}: ${point.count}회</title></circle>`).join('');
  return `<svg class="sparkline" viewBox="0 0 ${width} ${height}" role="img" aria-label="키워드 일별 등장 추이">
    <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" />
    <path d="${path}" />${dots}
  </svg>`;
}

function renderInsights() {
  const range = getDateRange(state.activeDate, state.period);
  const categories = [...state.insightCategories];
  const entries = flattenEntries(state.data, { ...range, categories });
  const keywords = analyzeKeywords(entries);
  const phrases = findTopPhrases(entries);
  const top = keywords[0];
  const summary = keywordSummary(entries, state.keywordQuery);

  $('#period-label').textContent = `${formatDate(range.startDate)} ~ ${formatDate(range.endDate)}`;
  $('#stat-total').textContent = entries.length.toLocaleString('ko-KR');
  $('#stat-keyword').textContent = top?.keyword ?? '—';
  $('#stat-keyword-sub').textContent = top ? `${top.count}회 · 순위점수 ${top.score}` : '데이터 없음';
  $('#stat-unique').textContent = new Set(entries.map(entry => entry.title)).size.toLocaleString('ko-KR');
  $('#stat-days').textContent = new Set(entries.map(entry => entry.date)).size.toLocaleString('ko-KR');
  $('#keyword-bars').innerHTML = renderBars(keywords);

  $('#phrase-list').innerHTML = phrases.length ? phrases.map(item => `
    <span class="phrase-pill">${escapeHtml(item.phrase)} <b>${item.count}</b></span>
  `).join('') : '<span class="muted">반복된 2어절 조합이 아직 없습니다.</span>';

  $('#keyword-result-title').textContent = `“${state.keywordQuery || '키워드'}” 분석`;
  $('#keyword-result-count').textContent = `${summary.count}회`;
  $('#keyword-result-score').textContent = `순위점수 ${summary.score}`;
  $('#keyword-result-rank').textContent = summary.averageRank === null ? '평균 순위 —' : `평균 ${summary.averageRank.toFixed(1)}위 · 최고 ${summary.bestRank}위`;
  $('#keyword-sparkline').innerHTML = renderSparkline(summary.byDate);
  $('#keyword-matches').innerHTML = summary.matches.length ? summary.matches.slice(0, 12).map(entry => `
    <div class="match-row"><span>${entry.date}</span><b>${CATEGORY_META[entry.category].short} ${entry.rank}위</b><p>${escapeHtml(entry.title)}</p></div>
  `).join('') : '<div class="empty-state compact">해당 키워드가 포함된 제목이 없습니다.</div>';

  $$('#keyword-bars .bar-row').forEach(button => {
    button.addEventListener('click', () => {
      state.keywordQuery = button.dataset.keyword;
      $('#keyword-input').value = state.keywordQuery;
      renderInsights();
    });
  });
}

function bindEvents() {
  $$('.nav-button').forEach(button => button.addEventListener('click', () => {
    state.activeView = button.dataset.view;
    renderNav();
  }));

  $('#title-date').addEventListener('change', event => {
    state.activeDate = event.target.value;
    $('#insight-date').value = state.activeDate;
    renderCategoryTabs();
    renderTitles();
    renderInsights();
  });

  $('#insight-date').addEventListener('change', event => {
    state.activeDate = event.target.value;
    $('#title-date').value = state.activeDate;
    renderCategoryTabs();
    renderTitles();
    renderInsights();
  });

  $('#title-search').addEventListener('input', event => {
    state.titleQuery = event.target.value;
    renderTitles();
  });

  $$('.period-button').forEach(button => button.addEventListener('click', () => {
    state.period = button.dataset.period;
    $$('.period-button').forEach(item => item.classList.toggle('active', item === button));
    renderInsights();
  }));

  $('#keyword-form').addEventListener('submit', event => {
    event.preventDefault();
    state.keywordQuery = $('#keyword-input').value.trim();
    renderInsights();
  });
}

async function init() {
  try {
    await loadData();
    renderDateSelects();
    renderCategoryTabs();
    renderInsightCategoryFilters();
    renderTitles();
    renderInsights();
    bindEvents();
    renderNav();
    $('#updated-at').textContent = `데이터 갱신 ${new Date(state.data.updatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`;
  } catch (error) {
    console.error(error);
    document.body.innerHTML = `<main class="fatal"><h1>데이터를 표시할 수 없습니다.</h1><p>${escapeHtml(error.message)}</p></main>`;
  }
}

init();
