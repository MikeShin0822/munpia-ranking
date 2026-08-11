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
