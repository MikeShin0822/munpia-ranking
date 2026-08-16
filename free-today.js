const freeTodayState = {
  index: null,
  day: null,
  date: '',
  snapshot: '',
  query: '',
  loaded: false
};

const ft$ = selector => document.querySelector(selector);
const ft$$ = selector => [...document.querySelectorAll(selector)];

function ftEscape(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

function ftFormatDate(date) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short'
  }).format(new Date(`${date}T12:00:00+09:00`));
}

function ftFormatDateTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function ftFormatTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function ftFormatNumber(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
    ? Number(value).toLocaleString('ko-KR')
    : '—';
}

function ensureFreeTodaySurface() {
  if (!document.querySelector('link[href="./free-today.css"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = './free-today.css';
    document.head.append(link);
  }

  const nav = document.querySelector('.main-nav');
  if (nav && !nav.querySelector('[data-view="free-today"]')) {
    const button = document.createElement('button');
    button.className = 'nav-button';
    button.dataset.view = 'free-today';
    button.textContent = '무료 투데이';
    const newBestButton = nav.querySelector('[data-view="new-best"]');
    if (newBestButton) newBestButton.insertAdjacentElement('afterend', button);
    else nav.append(button);
  }

  if (!document.querySelector('#free-today-view')) {
    const section = document.createElement('section');
    section.id = 'free-today-view';
    section.className = 'view-shell';
    section.hidden = true;
    section.innerHTML = `
      <div class="hero free-today-hero">
        <div>
          <p class="eyebrow">FREE TODAY RADAR</p>
          <h1>무료 투데이 200위의 흐름.</h1>
          <p>최근 24시간 무료 연재작의 본인 인증 조회수 순위를 6시간 간격으로 저장합니다. 기존 일간 30위와 신규 베스트 데이터와는 분리되어 있습니다.</p>
        </div>
        <div class="free-today-controls">
          <label class="date-control">날짜<select id="free-today-date"></select></label>
          <label class="date-control">수집 시점<select id="free-today-snapshot"></select></label>
        </div>
      </div>

      <div id="free-today-status" class="free-today-status"></div>

      <div class="stat-grid free-today-stat-grid">
        <article class="stat-card"><span>TOP 200 컷</span><strong id="free-cutoff-200">—</strong><small>200위 조회수</small></article>
        <article class="stat-card"><span>TOP 100 컷</span><strong id="free-cutoff-100">—</strong><small>100위 조회수</small></article>
        <article class="stat-card"><span>TOP 50 컷</span><strong id="free-cutoff-50">—</strong><small>50위 조회수</small></article>
        <article class="stat-card standout"><span>TOP 20 컷</span><strong id="free-cutoff-20">—</strong><small>20위 조회수</small></article>
      </div>

      <section class="free-today-movers" aria-labelledby="free-today-movers-heading">
        <div class="free-mover-section-header">
          <div><h2 id="free-today-movers-heading">급상승 · 급하락</h2><p>선택한 6시간 스냅샷과 직전 스냅샷의 동일 작품을 직접 비교합니다.</p></div>
          <small id="free-today-mover-meta">직전 스냅샷을 확인하는 중입니다.</small>
        </div>
        <div class="free-mover-grid">
          <article class="panel free-mover-panel">
            <div class="panel-header"><h3>급상승 TOP 5</h3><span>직전 수집 대비 상승 폭</span></div>
            <div id="free-today-rising" class="free-mover-list"></div>
          </article>
          <article class="panel free-mover-panel">
            <div class="panel-header"><h3>급하락 TOP 5</h3><span>직전 수집 대비 하락 폭</span></div>
            <div id="free-today-falling" class="free-mover-list"></div>
          </article>
        </div>
      </section>

      <section class="panel free-today-panel">
        <div class="panel-header">
          <div><h2>무료 투데이 1~200위</h2><p id="free-today-meta">수집 데이터를 불러오는 중입니다.</p></div>
          <label class="search-box"><span>검색</span><input id="free-today-search" type="search" placeholder="제목 · 작가 · 장르 검색"></label>
        </div>
        <div class="free-today-table-wrap">
          <div class="free-today-table-head" aria-hidden="true">
            <span>순위</span><span>작품</span><span>작가</span><span>장르</span><span>조회</span><span>변동</span>
          </div>
          <div id="free-today-list" class="free-today-list"></div>
        </div>
      </section>

      <section class="panel free-cutoff-chart-panel" aria-labelledby="free-cutoff-chart-heading">
        <div class="panel-header">
          <div><h2 id="free-cutoff-chart-heading">조회수 컷 일중 변화</h2><p id="free-cutoff-chart-meta">수집 시점별 TOP 20·50·100·200 조회수 컷을 비교합니다.</p></div>
        </div>
        <div id="free-cutoff-chart" class="free-cutoff-chart"></div>
      </section>
    `;
    const newBestView = document.querySelector('#new-best-view');
    if (newBestView) newBestView.insertAdjacentElement('afterend', section);
    else document.querySelector('main')?.append(section);
  }
}

async function loadFreeTodayDay(date) {
  if (!date) {
    freeTodayState.day = null;
    freeTodayState.snapshot = '';
    return;
  }
  const response = await fetch(`./data/free-today/${date}.json`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${date} 데이터 HTTP ${response.status}`);
  freeTodayState.day = await response.json();
  freeTodayState.snapshot = freeTodayState.day.snapshots?.at(-1)?.collectedAt || '';
}

async function loadFreeToday() {
  try {
    const response = await fetch('./data/free-today/index.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`인덱스 HTTP ${response.status}`);
    freeTodayState.index = await response.json();
    freeTodayState.date = freeTodayState.index.latestDate || freeTodayState.index.availableDates?.at(-1) || '';
    await loadFreeTodayDay(freeTodayState.date);
    freeTodayState.loaded = true;
  } catch (error) {
    console.warn('무료 투데이 데이터를 아직 불러올 수 없습니다.', error);
    freeTodayState.index = null;
    freeTodayState.day = null;
    freeTodayState.loaded = false;
  }
  renderFreeToday();
}

function currentFreeTodaySnapshot() {
  const snapshots = freeTodayState.day?.snapshots ?? [];
  if (!snapshots.length) return null;
  return snapshots.find(item => item.collectedAt === freeTodayState.snapshot) ?? snapshots.at(-1);
}

function previousFreeTodaySnapshot() {
  const snapshots = freeTodayState.day?.snapshots ?? [];
  const current = currentFreeTodaySnapshot();
  if (!current || snapshots.length < 2) return null;
  const index = snapshots.findIndex(item => item.collectedAt === current.collectedAt);
  return index > 0 ? snapshots[index - 1] : null;
}

function freeRankingIdentity(item) {
  if (item.unavailable) return `unavailable:${item.rank}`;
  return item.url || `${item.title}::${item.author || ''}`;
}

function calculateFreeMovers(current, previous) {
  if (!current || !previous) return { rising: [], falling: [] };
  const before = new Map(
    (previous.rankings ?? [])
      .filter(item => !item.unavailable)
      .map(item => [freeRankingIdentity(item), item])
  );
  const comparable = [];
  for (const item of current.rankings ?? []) {
    if (item.unavailable) continue;
    const old = before.get(freeRankingIdentity(item));
    if (!old || old.unavailable) continue;
    const delta = old.rank - item.rank;
    if (!delta) continue;
    comparable.push({ ...item, previousRank: old.rank, currentRank: item.rank, delta });
  }
  return {
    rising: comparable.filter(item => item.delta > 0)
      .sort((a, b) => b.delta - a.delta || a.currentRank - b.currentRank).slice(0, 5),
    falling: comparable.filter(item => item.delta < 0)
      .sort((a, b) => a.delta - b.delta || b.currentRank - a.currentRank).slice(0, 5)
  };
}

function renderFreeTodayControls() {
  const dates = [...(freeTodayState.index?.availableDates ?? [])].reverse();
  const dateSelect = ft$('#free-today-date');
  const snapshotSelect = ft$('#free-today-snapshot');
  if (!dateSelect || !snapshotSelect) return;
  if (!dates.length) {
    dateSelect.innerHTML = '<option>데이터 준비 중</option>';
    dateSelect.disabled = true;
    snapshotSelect.innerHTML = '<option>—</option>';
    snapshotSelect.disabled = true;
    return;
  }
  dateSelect.disabled = false;
  dateSelect.innerHTML = dates.map(date => `<option value="${date}">${ftFormatDate(date)}</option>`).join('');
  dateSelect.value = freeTodayState.date;
  const snapshots = [...(freeTodayState.day?.snapshots ?? [])].reverse();
  snapshotSelect.disabled = !snapshots.length;
  snapshotSelect.innerHTML = snapshots.length
    ? snapshots.map(item => `<option value="${ftEscape(item.collectedAt)}">${ftFormatDateTime(item.aggregateAt || item.collectedAt)} 집계</option>`).join('')
    : '<option>수집 데이터 없음</option>';
  if (freeTodayState.snapshot) snapshotSelect.value = freeTodayState.snapshot;
}

function freeChangeMarkup(item) {
  if (item.unavailable) return '<span class="free-rank-change unavailable">비노출</span>';
  const type = item.changeType || 'unknown';
  if (type === 'new') return '<span class="free-rank-change new">NEW</span>';
  if (type === 'up') return `<span class="free-rank-change up">▲ ${ftEscape(item.change || '')}</span>`;
  if (type === 'down') return `<span class="free-rank-change down">▼ ${ftEscape(item.change || '')}</span>`;
  if (type === 'same') return '<span class="free-rank-change same">—</span>';
  return `<span class="free-rank-change unknown">${ftEscape(item.change || '—')}</span>`;
}

function freeMoverMarkup(item, direction) {
  const isUp = direction === 'up';
  return `
    <a class="free-mover-row" href="${ftEscape(item.url || '#')}" target="_blank" rel="noopener noreferrer">
      <span class="free-mover-delta ${isUp ? 'up' : 'down'}">${isUp ? '▲' : '▼'} ${Math.abs(item.delta)}</span>
      <span class="free-mover-title">${ftEscape(item.title)}</span>
      <span class="free-mover-ranks">${item.previousRank}위 → <b>${item.currentRank}위</b></span>
      <span class="free-mover-views">조회 ${ftFormatNumber(item.views)}</span>
    </a>
  `;
}

function renderFreeMovers(snapshot) {
  const previous = previousFreeTodaySnapshot();
  const risingNode = ft$('#free-today-rising');
  const fallingNode = ft$('#free-today-falling');
  const metaNode = ft$('#free-today-mover-meta');
  if (!risingNode || !fallingNode || !metaNode) return;
  if (!snapshot || !previous) {
    metaNode.textContent = '직전 스냅샷이 생기면 자동으로 비교합니다.';
    const empty = '<div class="free-mover-empty">비교할 이전 수집 시점이 없습니다.</div>';
    risingNode.innerHTML = empty;
    fallingNode.innerHTML = empty;
    return;
  }
  const movers = calculateFreeMovers(snapshot, previous);
  metaNode.textContent = `${ftFormatDateTime(previous.aggregateAt || previous.collectedAt)} → ${ftFormatDateTime(snapshot.aggregateAt || snapshot.collectedAt)} · 동일 작품 직접 비교`;
  risingNode.innerHTML = movers.rising.length
    ? movers.rising.map(item => freeMoverMarkup(item, 'up')).join('')
    : '<div class="free-mover-empty">이 구간에서 상승한 비교 가능 작품이 없습니다.</div>';
  fallingNode.innerHTML = movers.falling.length
    ? movers.falling.map(item => freeMoverMarkup(item, 'down')).join('')
    : '<div class="free-mover-empty">이 구간에서 하락한 비교 가능 작품이 없습니다.</div>';
}

function renderFreeCutoffChart() {
  const container = ft$('#free-cutoff-chart');
  const meta = ft$('#free-cutoff-chart-meta');
  if (!container || !meta) return;
  const snapshots = [...(freeTodayState.day?.snapshots ?? [])]
    .sort((a, b) => String(a.aggregateAt || a.collectedAt).localeCompare(String(b.aggregateAt || b.collectedAt)));
  if (snapshots.length < 2) {
    meta.textContent = '하루에 스냅샷이 2개 이상 쌓이면 일중 변화를 그립니다.';
    container.innerHTML = '<div class="free-cutoff-chart-empty">그래프를 만들기 위한 수집 시점이 아직 부족합니다.</div>';
    return;
  }

  const series = [
    { rank: '20', label: 'TOP 20', className: 'free-cutoff-line-20' },
    { rank: '50', label: 'TOP 50', className: 'free-cutoff-line-50' },
    { rank: '100', label: 'TOP 100', className: 'free-cutoff-line-100' },
    { rank: '200', label: 'TOP 200', className: 'free-cutoff-line-200' }
  ];
  const numeric = value => value === null || value === undefined ? null : Number(value);
  const values = snapshots.flatMap(snapshot => series
    .map(item => numeric(snapshot.cutoffs?.[item.rank]))
    .filter(Number.isFinite));
  const maxValue = Math.max(...values, 1);
  const width = 980;
  const height = 310;
  const left = 58;
  const right = 24;
  const top = 24;
  const bottom = 52;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const x = index => left + index * (chartWidth / Math.max(1, snapshots.length - 1));
  const y = value => top + (1 - Number(value) / maxValue) * chartHeight;
  const selected = currentFreeTodaySnapshot();
  const selectedIndex = snapshots.findIndex(item => item.collectedAt === selected?.collectedAt);

  const grid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const value = Math.round(maxValue * (1 - ratio));
    const yy = top + ratio * chartHeight;
    return `<g class="free-cutoff-grid"><line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}"/><text x="${left - 10}" y="${yy + 4}" text-anchor="end">${ftFormatNumber(value)}</text></g>`;
  }).join('');

  const marker = selectedIndex >= 0
    ? `<line class="free-cutoff-selected-marker" x1="${x(selectedIndex)}" y1="${top}" x2="${x(selectedIndex)}" y2="${height - bottom}"/>`
    : '';

  const lines = series.map(item => {
    const points = snapshots.map((snapshot, index) => {
      const value = numeric(snapshot.cutoffs?.[item.rank]);
      return {
        x: x(index), value,
        y: Number.isFinite(value) ? y(value) : null,
        time: ftFormatTime(snapshot.aggregateAt || snapshot.collectedAt),
        selected: snapshot.collectedAt === selected?.collectedAt
      };
    }).filter(point => point.y !== null);
    const path = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ');
    const dots = points.map(point => `<circle class="${point.selected ? 'selected' : ''}" cx="${point.x}" cy="${point.y}" r="${point.selected ? 5.5 : 4}"><title>${item.label} · ${point.time} · ${ftFormatNumber(point.value)}회</title></circle>`).join('');
    return `<g class="free-cutoff-series ${item.className}"><path d="${path}"/>${dots}</g>`;
  }).join('');

  const labels = snapshots.map((snapshot, index) => `<text class="free-cutoff-x-label" x="${x(index)}" y="${height - 18}" text-anchor="middle">${ftFormatTime(snapshot.aggregateAt || snapshot.collectedAt)}</text>`).join('');
  const legend = series.map(item => `<span class="free-cutoff-legend-item ${item.className}"><i></i>${item.label}</span>`).join('');
  meta.textContent = `${snapshots.length}개 수집 시점 · 문피아 집계시각 기준 · 점에 마우스를 올리면 조회수 컷을 확인할 수 있습니다.`;
  container.innerHTML = `
    <div class="free-cutoff-legend">${legend}</div>
    <div class="free-cutoff-svg-wrap">
      <svg class="free-cutoff-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="무료 투데이 조회수 컷 일중 변화">
        ${grid}${marker}${lines}${labels}
      </svg>
    </div>
  `;
}

function freeRankingRow(item) {
  const work = item.unavailable
    ? `<span class="free-work-title unavailable">${ftEscape(item.title)}</span><small>${ftEscape(item.unavailableReason || '세부 정보 비공개')}</small>`
    : `<a href="${ftEscape(item.url || '#')}" target="_blank" rel="noopener noreferrer">${ftEscape(item.title)}</a><small>${item.hours == null ? '' : `${item.hours}시간 전 연재`}</small>`;
  return `
    <article class="free-today-row ${item.unavailable ? 'unavailable' : ''}">
      <div class="free-today-rank ${item.rank <= 3 ? 'top' : ''}">${item.rank}</div>
      <div class="free-today-work">${work}</div>
      <div class="free-today-author">${ftEscape(item.author || '—')}</div>
      <div class="free-today-genre">${ftEscape((item.genres ?? []).join(' · ') || '—')}</div>
      <div class="free-today-views">${ftFormatNumber(item.views)}</div>
      <div>${freeChangeMarkup(item)}</div>
    </article>
  `;
}

function renderFreeToday() {
  renderFreeTodayControls();
  const snapshot = currentFreeTodaySnapshot();
  const list = ft$('#free-today-list');
  if (!list) return;
  if (!snapshot) {
    ['#free-cutoff-200', '#free-cutoff-100', '#free-cutoff-50', '#free-cutoff-20'].forEach(selector => {
      const node = ft$(selector);
      if (node) node.textContent = '—';
    });
    ft$('#free-today-status').innerHTML = '<div class="free-today-notice">첫 무료 투데이 수집을 준비 중입니다. 기존 데이터와 독립적으로 표시됩니다.</div>';
    ft$('#free-today-meta').textContent = '아직 저장된 무료 투데이 스냅샷이 없습니다.';
    list.innerHTML = '<div class="empty-state">무료 투데이 데이터가 아직 없습니다.</div>';
    renderFreeMovers(null);
    renderFreeCutoffChart();
    return;
  }

  ft$('#free-cutoff-200').textContent = ftFormatNumber(snapshot.cutoffs?.['200']);
  ft$('#free-cutoff-100').textContent = ftFormatNumber(snapshot.cutoffs?.['100']);
  ft$('#free-cutoff-50').textContent = ftFormatNumber(snapshot.cutoffs?.['50']);
  ft$('#free-cutoff-20').textContent = ftFormatNumber(snapshot.cutoffs?.['20']);

  const aggregate = snapshot.aggregateAt ? `문피아 집계 ${ftFormatDateTime(snapshot.aggregateAt)}` : '문피아 집계시각 미확인';
  const collected = `수집 ${ftFormatDateTime(snapshot.collectedAt)}`;
  const unavailable = Number(snapshot.unavailableCount || 0);
  const visibility = unavailable
    ? ` · 공개 페이지 비노출 ${unavailable}개 순위 (${(snapshot.unavailableRanks ?? []).join(', ')}위)`
    : '';
  const statusText = snapshot.status === 'complete' ? '1~200위 순위 슬롯 정상 수집' : `${snapshot.count ?? 0}/200 일부 수집`;
  ft$('#free-today-status').innerHTML = `<div class="free-today-notice"><b>${statusText}</b><span>${aggregate} · ${collected}${visibility}</span></div>`;
  ft$('#free-today-meta').textContent = `${aggregate} · 공개 작품 ${snapshot.visibleCount ?? snapshot.rankings?.filter(item => !item.unavailable).length ?? 0}개 · 전체 순위 슬롯 ${snapshot.rankings?.length ?? 0}개`;

  renderFreeMovers(snapshot);
  renderFreeCutoffChart();

  const query = freeTodayState.query.trim().toLocaleLowerCase('ko-KR');
  const rankings = snapshot.rankings ?? [];
  const filtered = rankings.filter(item => {
    if (!query) return true;
    return [item.title, item.author, ...(item.genres ?? []), item.unavailableReason]
      .join(' ').toLocaleLowerCase('ko-KR').includes(query);
  });
  list.innerHTML = filtered.length
    ? filtered.map(freeRankingRow).join('')
    : '<div class="empty-state">검색 조건에 맞는 작품이 없습니다.</div>';
}

function showFreeTodayView(active) {
  const view = ft$('#free-today-view');
  if (!view) return;
  view.hidden = !active;
  if (active) {
    ft$('#titles-view')?.setAttribute('hidden', '');
    ft$('#insights-view')?.setAttribute('hidden', '');
    ft$('#new-best-view')?.setAttribute('hidden', '');
    ft$('#weekly-patterns-view')?.setAttribute('hidden', '');
    ft$$('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === 'free-today'));
    if (!freeTodayState.loaded) loadFreeToday();
    if (ft$('#updated-at') && freeTodayState.index?.updatedAt) {
      ft$('#updated-at').textContent = `무료 투데이 갱신 ${ftFormatDateTime(freeTodayState.index.updatedAt)}`;
    }
  }
}

function bindFreeTodayEvents() {
  ft$('.main-nav')?.addEventListener('click', event => {
    const button = event.target.closest('.nav-button');
    if (!button) return;
    showFreeTodayView(button.dataset.view === 'free-today');
  });
  ft$('#free-today-date')?.addEventListener('change', async event => {
    freeTodayState.date = event.target.value;
    try {
      await loadFreeTodayDay(freeTodayState.date);
    } catch (error) {
      console.warn(error);
      freeTodayState.day = null;
    }
    renderFreeToday();
  });
  ft$('#free-today-snapshot')?.addEventListener('change', event => {
    freeTodayState.snapshot = event.target.value;
    renderFreeToday();
  });
  ft$('#free-today-search')?.addEventListener('input', event => {
    freeTodayState.query = event.target.value;
    renderFreeToday();
  });
}

ensureFreeTodaySurface();
bindFreeTodayEvents();
loadFreeToday();
