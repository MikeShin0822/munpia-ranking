const newBestState = {
  index: null,
  day: null,
  date: '',
  snapshot: '',
  query: '',
  loaded: false
};

const nb$ = selector => document.querySelector(selector);
const nb$$ = selector => [...document.querySelectorAll(selector)];

function nbEscape(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

function nbFormatDate(date) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short'
  }).format(new Date(`${date}T12:00:00+09:00`));
}

function nbFormatDateTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function nbFormatTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function nbFormatNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString('ko-KR') : '—';
}

async function loadNewBestDay(date) {
  if (!date) {
    newBestState.day = null;
    newBestState.snapshot = '';
    return;
  }
  const response = await fetch(`./data/new-best/${date}.json`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${date} 데이터 HTTP ${response.status}`);
  newBestState.day = await response.json();
  newBestState.snapshot = newBestState.day.snapshots?.at(-1)?.collectedAt || '';
}

async function loadNewBest() {
  try {
    const response = await fetch('./data/new-best/index.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`인덱스 HTTP ${response.status}`);
    newBestState.index = await response.json();
    newBestState.date = newBestState.index.latestDate || newBestState.index.availableDates?.at(-1) || '';
    await loadNewBestDay(newBestState.date);
    newBestState.loaded = true;
  } catch (error) {
    console.warn('신규 베스트 데이터를 아직 불러올 수 없습니다.', error);
    newBestState.index = null;
    newBestState.day = null;
    newBestState.loaded = false;
  }
  renderNewBest();
}

function currentNewBestSnapshot() {
  const snapshots = newBestState.day?.snapshots ?? [];
  if (!snapshots.length) return null;
  return snapshots.find(item => item.collectedAt === newBestState.snapshot) ?? snapshots.at(-1);
}

function previousNewBestSnapshot() {
  const snapshots = newBestState.day?.snapshots ?? [];
  const current = currentNewBestSnapshot();
  if (!current || snapshots.length < 2) return null;
  const index = snapshots.findIndex(item => item.collectedAt === current.collectedAt);
  return index > 0 ? snapshots[index - 1] : null;
}

function rankingIdentity(item) {
  return item.url || `${item.title}::${item.author || ''}`;
}

function calculateMovers(current, previous) {
  if (!current || !previous) return { rising: [], falling: [] };
  const before = new Map((previous.rankings ?? []).map(item => [rankingIdentity(item), item]));
  const comparable = [];

  for (const item of current.rankings ?? []) {
    const old = before.get(rankingIdentity(item));
    if (!old) continue;
    const delta = old.rank - item.rank;
    if (!delta) continue;
    comparable.push({
      ...item,
      previousRank: old.rank,
      currentRank: item.rank,
      delta
    });
  }

  const rising = comparable
    .filter(item => item.delta > 0)
    .sort((a, b) => b.delta - a.delta || a.currentRank - b.currentRank)
    .slice(0, 5);
  const falling = comparable
    .filter(item => item.delta < 0)
    .sort((a, b) => a.delta - b.delta || b.currentRank - a.currentRank)
    .slice(0, 5);
  return { rising, falling };
}

function renderNewBestControls() {
  const dates = [...(newBestState.index?.availableDates ?? [])].reverse();
  const dateSelect = nb$('#new-best-date');
  const snapshotSelect = nb$('#new-best-snapshot');
  if (!dateSelect || !snapshotSelect) return;

  if (!dates.length) {
    dateSelect.innerHTML = '<option>데이터 준비 중</option>';
    dateSelect.disabled = true;
    snapshotSelect.innerHTML = '<option>—</option>';
    snapshotSelect.disabled = true;
    return;
  }

  dateSelect.disabled = false;
  dateSelect.innerHTML = dates.map(date => `<option value="${date}">${nbFormatDate(date)}</option>`).join('');
  dateSelect.value = newBestState.date;

  const snapshots = [...(newBestState.day?.snapshots ?? [])].reverse();
  snapshotSelect.disabled = !snapshots.length;
  snapshotSelect.innerHTML = snapshots.length
    ? snapshots.map(item => `<option value="${nbEscape(item.collectedAt)}">${nbFormatDateTime(item.collectedAt)} 수집</option>`).join('')
    : '<option>수집 데이터 없음</option>';
  if (newBestState.snapshot) snapshotSelect.value = newBestState.snapshot;
}

function changeMarkup(item) {
  const type = item.changeType || 'unknown';
  if (type === 'new') return '<span class="rank-change new">NEW</span>';
  if (type === 'up') return `<span class="rank-change up">▲ ${nbEscape(item.change || '')}</span>`;
  if (type === 'down') return `<span class="rank-change down">▼ ${nbEscape(item.change || '')}</span>`;
  if (type === 'same') return '<span class="rank-change same">—</span>';
  return `<span class="rank-change unknown">${nbEscape(item.change || '—')}</span>`;
}

function moverMarkup(item, direction) {
  const isUp = direction === 'up';
  return `
    <a class="mover-row" href="${nbEscape(item.url || '#')}" target="_blank" rel="noopener noreferrer">
      <span class="mover-delta ${isUp ? 'up' : 'down'}">${isUp ? '▲' : '▼'} ${Math.abs(item.delta)}</span>
      <span class="mover-title">${nbEscape(item.title)}</span>
      <span class="mover-ranks">${item.previousRank}위 → <b>${item.currentRank}위</b></span>
      <span class="mover-views">조회 ${nbFormatNumber(item.views)}</span>
    </a>
  `;
}

function renderMovers(snapshot) {
  const previous = previousNewBestSnapshot();
  const risingNode = nb$('#new-best-rising');
  const fallingNode = nb$('#new-best-falling');
  const metaNode = nb$('#new-best-mover-meta');
  if (!risingNode || !fallingNode || !metaNode) return;

  if (!snapshot || !previous) {
    metaNode.textContent = '직전 스냅샷이 생기면 자동으로 비교합니다.';
    const empty = '<div class="mover-empty">비교할 이전 수집 시점이 없습니다.</div>';
    risingNode.innerHTML = empty;
    fallingNode.innerHTML = empty;
    return;
  }

  const movers = calculateMovers(snapshot, previous);
  metaNode.textContent = `${nbFormatDateTime(previous.aggregateAt || previous.collectedAt)} → ${nbFormatDateTime(snapshot.aggregateAt || snapshot.collectedAt)} · 동일 작품 직접 비교`;
  risingNode.innerHTML = movers.rising.length
    ? movers.rising.map(item => moverMarkup(item, 'up')).join('')
    : '<div class="mover-empty">이 구간에서 상승한 비교 가능 작품이 없습니다.</div>';
  fallingNode.innerHTML = movers.falling.length
    ? movers.falling.map(item => moverMarkup(item, 'down')).join('')
    : '<div class="mover-empty">이 구간에서 하락한 비교 가능 작품이 없습니다.</div>';
}

function renderCutoffChart() {
  const container = nb$('#cutoff-chart');
  const meta = nb$('#cutoff-chart-meta');
  if (!container || !meta) return;
  const snapshots = [...(newBestState.day?.snapshots ?? [])].sort((a, b) => String(a.collectedAt).localeCompare(String(b.collectedAt)));

  if (snapshots.length < 2) {
    meta.textContent = '하루에 스냅샷이 2개 이상 쌓이면 일중 변화를 그립니다.';
    container.innerHTML = '<div class="cutoff-chart-empty">그래프를 만들기 위한 수집 시점이 아직 부족합니다.</div>';
    return;
  }

  const series = [
    { rank: '20', label: 'TOP 20', className: 'cutoff-line-20' },
    { rank: '50', label: 'TOP 50', className: 'cutoff-line-50' },
    { rank: '100', label: 'TOP 100', className: 'cutoff-line-100' },
    { rank: '200', label: 'TOP 200', className: 'cutoff-line-200' }
  ];
  const values = snapshots.flatMap(snapshot => series.map(item => Number(snapshot.cutoffs?.[item.rank])).filter(Number.isFinite));
  const maxValue = Math.max(...values, 1);
  const width = 980;
  const height = 310;
  const left = 58;
  const right = 24;
  const top = 24;
  const bottom = 52;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const x = index => snapshots.length === 1 ? left + chartWidth / 2 : left + index * (chartWidth / (snapshots.length - 1));
  const y = value => top + (1 - Number(value || 0) / maxValue) * chartHeight;
  const selectedIndex = snapshots.findIndex(item => item.collectedAt === currentNewBestSnapshot()?.collectedAt);

  const grid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const value = Math.round(maxValue * (1 - ratio));
    const yy = top + ratio * chartHeight;
    return `<g class="cutoff-grid"><line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}"/><text x="${left - 10}" y="${yy + 4}" text-anchor="end">${nbFormatNumber(value)}</text></g>`;
  }).join('');

  const selectedMarker = selectedIndex >= 0
    ? `<line class="cutoff-selected-marker" x1="${x(selectedIndex)}" y1="${top}" x2="${x(selectedIndex)}" y2="${height - bottom}" />`
    : '';

  const lines = series.map(item => {
    const points = snapshots.map((snapshot, index) => ({
      x: x(index),
      y: y(snapshot.cutoffs?.[item.rank]),
      value: snapshot.cutoffs?.[item.rank],
      time: nbFormatTime(snapshot.aggregateAt || snapshot.collectedAt),
      selected: snapshot.collectedAt === currentNewBestSnapshot()?.collectedAt
    }));
    const path = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ');
    const dots = points.map(point => `<circle class="cutoff-point ${point.selected ? 'selected' : ''}" cx="${point.x}" cy="${point.y}" r="${point.selected ? 5.5 : 4}"><title>${item.label} · ${point.time} · ${nbFormatNumber(point.value)}회</title></circle>`).join('');
    return `<g class="cutoff-series ${item.className}"><path d="${path}"/>${dots}</g>`;
  }).join('');

  const xLabels = snapshots.map((snapshot, index) => `<text class="cutoff-x-label" x="${x(index)}" y="${height - 18}" text-anchor="middle">${nbFormatTime(snapshot.aggregateAt || snapshot.collectedAt)}</text>`).join('');
  const legend = series.map(item => `<span class="cutoff-legend-item ${item.className}"><i></i>${item.label}</span>`).join('');

  meta.textContent = `${snapshots.length}개 수집 시점 · 문피아 집계시각 기준 · 점에 마우스를 올리면 조회수 컷을 확인할 수 있습니다.`;
  container.innerHTML = `
    <div class="cutoff-legend">${legend}</div>
    <div class="cutoff-svg-wrap">
      <svg class="cutoff-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="신규 베스트 조회수 컷 일중 변화">
        ${grid}${selectedMarker}${lines}${xLabels}
      </svg>
    </div>
  `;
}

function renderNewBest() {
  renderNewBestControls();
  const snapshot = currentNewBestSnapshot();
  const list = nb$('#new-best-list');
  if (!list) return;

  if (!snapshot) {
    ['#cutoff-200', '#cutoff-100', '#cutoff-50', '#cutoff-20'].forEach(selector => {
      const node = nb$(selector);
      if (node) node.textContent = '—';
    });
    nb$('#new-best-status').innerHTML = '<div class="new-best-notice">첫 신규 베스트 수집을 준비 중입니다. 기존 제목/통계 데이터와는 독립적으로 표시됩니다.</div>';
    nb$('#new-best-meta').textContent = '아직 저장된 신규 베스트 스냅샷이 없습니다.';
    list.innerHTML = '<div class="empty-state">신규 베스트 데이터가 아직 없습니다.</div>';
    renderMovers(null);
    renderCutoffChart();
    return;
  }

  nb$('#cutoff-200').textContent = nbFormatNumber(snapshot.cutoffs?.['200']);
  nb$('#cutoff-100').textContent = nbFormatNumber(snapshot.cutoffs?.['100']);
  nb$('#cutoff-50').textContent = nbFormatNumber(snapshot.cutoffs?.['50']);
  nb$('#cutoff-20').textContent = nbFormatNumber(snapshot.cutoffs?.['20']);

  const aggregate = snapshot.aggregateAt ? `문피아 집계 ${nbFormatDateTime(snapshot.aggregateAt)}` : '문피아 집계시각 미확인';
  const collected = `수집 ${nbFormatDateTime(snapshot.collectedAt)}`;
  const statusText = snapshot.status === 'complete' ? '200/200 정상 수집' : `${snapshot.count ?? 0}/200 일부 수집`;
  nb$('#new-best-status').innerHTML = `<div class="new-best-notice"><b>${statusText}</b><span>${aggregate} · ${collected}</span></div>`;
  nb$('#new-best-meta').textContent = `${aggregate} · ${snapshot.rankings?.length ?? 0}개 작품`;

  renderMovers(snapshot);
  renderCutoffChart();

  const query = newBestState.query.trim().toLocaleLowerCase('ko-KR');
  const rankings = snapshot.rankings ?? [];
  const filtered = rankings.filter(item => {
    if (!query) return true;
    return [item.title, item.author, ...(item.genres ?? [])].join(' ').toLocaleLowerCase('ko-KR').includes(query);
  });

  list.innerHTML = filtered.length ? filtered.map(item => `
    <article class="new-best-row">
      <div class="new-best-rank ${item.rank <= 3 ? 'top' : ''}">${item.rank}</div>
      <div class="new-best-work">
        <a href="${nbEscape(item.url || '#')}" target="_blank" rel="noopener noreferrer">${nbEscape(item.title)}</a>
        <small>${item.hours == null ? '' : `${item.hours}시간 전 연재`}</small>
      </div>
      <div class="new-best-author">${nbEscape(item.author || '—')}</div>
      <div class="new-best-genre">${nbEscape((item.genres ?? []).join(' · ') || '—')}</div>
      <div class="new-best-views">${nbFormatNumber(item.views)}</div>
      <div>${changeMarkup(item)}</div>
    </article>
  `).join('') : '<div class="empty-state">검색 조건에 맞는 작품이 없습니다.</div>';
}

function showNewBestView(active) {
  const view = nb$('#new-best-view');
  if (view) view.hidden = !active;
  if (active) {
    const updated = nb$('#updated-at');
    if (updated && newBestState.index?.updatedAt) {
      updated.textContent = `신규 베스트 갱신 ${new Date(newBestState.index.updatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`;
    }
    if (!newBestState.loaded) loadNewBest();
  }
}

function bindNewBestEvents() {
  nb$$('.nav-button').forEach(button => {
    button.addEventListener('click', () => showNewBestView(button.dataset.view === 'new-best'));
  });

  nb$('#new-best-date')?.addEventListener('change', async event => {
    newBestState.date = event.target.value;
    try {
      await loadNewBestDay(newBestState.date);
    } catch (error) {
      console.warn(error);
      newBestState.day = null;
    }
    renderNewBest();
  });

  nb$('#new-best-snapshot')?.addEventListener('change', event => {
    newBestState.snapshot = event.target.value;
    renderNewBest();
  });

  nb$('#new-best-search')?.addEventListener('input', event => {
    newBestState.query = event.target.value;
    renderNewBest();
  });
}

bindNewBestEvents();
loadNewBest();
