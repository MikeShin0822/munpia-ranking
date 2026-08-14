const weeklyState = {
  index: null,
  report: null,
  key: '',
  loaded: false
};

const wp$ = selector => document.querySelector(selector);
const wp$$ = selector => [...document.querySelectorAll(selector)];

function wpEscape(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

function wpNumber(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return number.toLocaleString('ko-KR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

function wpDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short'
  }).format(new Date(`${value}T12:00:00+09:00`));
}

function wpDateTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).format(new Date(value));
}

function ensureWeeklySurface() {
  if (!document.querySelector('link[href="./weekly-patterns.css"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = './weekly-patterns.css';
    document.head.append(link);
  }

  const nav = document.querySelector('.main-nav');
  if (nav && !nav.querySelector('[data-view="weekly-patterns"]')) {
    const button = document.createElement('button');
    button.className = 'nav-button';
    button.dataset.view = 'weekly-patterns';
    button.textContent = '주간 패턴';
    nav.append(button);
  }

  const main = document.querySelector('main');
  if (main && !document.querySelector('#weekly-patterns-view')) {
    main.insertAdjacentHTML('beforeend', `
      <section id="weekly-patterns-view" class="view-shell" hidden>
        <div class="hero weekly-pattern-hero">
          <div>
            <p class="eyebrow">WEEKLY TITLE GRAMMAR</p>
            <h1>제목의 문법을 주간 단위로 읽습니다.</h1>
            <p>단어 빈도를 넘어 반복되는 제목 구조, 전주 대비 변화, 카테고리별 분포와 실제 순위 성과를 함께 살펴봅니다.</p>
          </div>
          <label class="date-control weekly-report-control">분석 주간
            <select id="weekly-pattern-select"></select>
          </label>
        </div>

        <div id="weekly-pattern-status" class="weekly-pattern-status"></div>

        <div class="stat-grid weekly-pattern-stats">
          <article class="stat-card"><span>고유 제목</span><strong id="weekly-stat-titles">—</strong><small>주간 중복 제거</small></article>
          <article class="stat-card standout"><span>대표 문법</span><strong id="weekly-stat-headline">—</strong><small>가장 넓게 반복된 구조</small></article>
          <article class="stat-card"><span>분석 패턴</span><strong id="weekly-stat-patterns">—</strong><small>주요 구조만 선별</small></article>
          <article class="stat-card"><span>수집 일수</span><strong id="weekly-stat-days">—</strong><small>월요일~일요일</small></article>
        </div>

        <div class="weekly-overview-grid">
          <section class="panel weekly-highlights-panel">
            <div class="panel-header"><div><p class="eyebrow">WEEKLY SHIFTS</p><h2>이번 주 핵심 변화</h2></div></div>
            <ol id="weekly-highlights" class="weekly-highlights"></ol>
          </section>
          <section class="panel weekly-change-panel">
            <div class="panel-header"><div><p class="eyebrow">WEEK OVER WEEK</p><h2>상승·약화 신호</h2></div></div>
            <div class="weekly-change-groups">
              <div><span>상승 패턴</span><div id="weekly-rising" class="weekly-change-list"></div></div>
              <div><span>약화 패턴</span><div id="weekly-falling" class="weekly-change-list"></div></div>
            </div>
          </section>
        </div>

        <section class="weekly-pattern-section" aria-labelledby="weekly-pattern-heading">
          <div class="weekly-section-header">
            <div><p class="eyebrow">PATTERN LIBRARY</p><h2 id="weekly-pattern-heading">이번 주 제목 패턴</h2></div>
            <p>하나의 제목이 두 가지 이상의 문법에 동시에 포함될 수 있습니다.</p>
          </div>
          <div id="weekly-pattern-list" class="weekly-pattern-list"></div>
        </section>

        <div class="weekly-bottom-grid">
          <section class="panel weekly-new-best-panel">
            <div class="panel-header"><div><p class="eyebrow">NEW BEST LINK</p><h2>신규베스트 초기 성과</h2></div></div>
            <div id="weekly-new-best-note" class="weekly-note-body"></div>
          </section>
          <section class="panel weekly-conclusion-panel">
            <div class="panel-header"><div><p class="eyebrow">ONE-LINE READ</p><h2>이번 주 한 줄 결론</h2></div></div>
            <blockquote id="weekly-conclusion"></blockquote>
            <div id="weekly-watchlist" class="weekly-watchlist"></div>
          </section>
        </div>

        <p id="weekly-method-note" class="weekly-method-note"></p>
      </section>
    `);
  }
}

async function loadWeeklyIndex() {
  const response = await fetch('./data/weekly-patterns/index.json', { cache: 'no-store' });
  if (!response.ok) throw new Error(`주간 리포트 인덱스 HTTP ${response.status}`);
  weeklyState.index = await response.json();
  weeklyState.key = weeklyState.index.latestKey || weeklyState.index.reports?.at(-1)?.key || '';
}

async function loadWeeklyReport(key) {
  if (!key) throw new Error('선택할 주간 리포트가 없습니다.');
  const response = await fetch(`./data/weekly-patterns/${encodeURIComponent(key)}.json`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`주간 리포트 HTTP ${response.status}`);
  weeklyState.report = await response.json();
  weeklyState.key = key;
}

async function loadWeeklyPatterns() {
  try {
    await loadWeeklyIndex();
    await loadWeeklyReport(weeklyState.key);
    weeklyState.loaded = true;
    renderWeeklyPatterns();
  } catch (error) {
    console.warn('주간 패턴 리포트를 불러오지 못했습니다.', error);
    weeklyState.loaded = false;
    const status = wp$('#weekly-pattern-status');
    if (status) status.innerHTML = `<div class="weekly-alert error">${wpEscape(error.message)}</div>`;
    const list = wp$('#weekly-pattern-list');
    if (list) list.innerHTML = '<div class="empty-state">주간 패턴 리포트가 아직 없습니다.</div>';
  }
}

function patternMap(report) {
  return new Map((report?.patterns ?? []).map(item => [item.key, item]));
}

function trendClass(value) {
  if (value === '강한 상승' || value === '상승' || value === '새로 등장') return 'rise';
  if (value === '하락') return 'fall';
  return 'steady';
}

function renderChangeList(keys, fallback) {
  const map = patternMap(weeklyState.report);
  const items = (keys ?? []).map(key => map.get(key)).filter(Boolean);
  if (!items.length) return `<span class="weekly-muted">${wpEscape(fallback)}</span>`;
  return items.map(item => `
    <span class="weekly-change-chip ${trendClass(item.trend)}">
      ${wpEscape(item.name)} <b>${item.change > 0 ? '+' : ''}${item.change}</b>
    </span>
  `).join('');
}

function renderPatternCard(item, index) {
  const categoryTotal = Object.values(item.categories ?? {}).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
  const categories = Object.entries(item.categories ?? {}).map(([label, count]) => `
    <div class="weekly-category-row">
      <span>${wpEscape(label)}</span>
      <i><b style="width:${Math.max(4, Number(count) / categoryTotal * 100)}%"></b></i>
      <em>${wpNumber(count)}</em>
    </div>
  `).join('');
  const representatives = (item.representativeTitles ?? []).map(title => `<li>${wpEscape(title)}</li>`).join('');
  return `
    <article class="panel weekly-pattern-card">
      <div class="weekly-pattern-card-head">
        <span class="weekly-pattern-index">${String(index + 1).padStart(2, '0')}</span>
        <div><h3>${wpEscape(item.name)}</h3><p>${wpEscape(item.formula)}</p></div>
        <div class="weekly-pattern-badges">
          <span class="weekly-trend ${trendClass(item.trend)}">${wpEscape(item.trend)} ${item.change ? `(${item.change > 0 ? '+' : ''}${item.change})` : ''}</span>
          <span class="weekly-life">${wpEscape(item.lifeStage)}</span>
        </div>
      </div>
      <div class="weekly-pattern-metrics">
        <div><span>고유 제목</span><strong>${wpNumber(item.uniqueTitleCount)}</strong><small>전체의 ${wpNumber(item.sharePercent, 1)}%</small></div>
        <div><span>평균 순위</span><strong>${wpNumber(item.averageRank, 1)}</strong><small>최고 ${wpNumber(item.bestRank)}위</small></div>
        <div><span>TOP 10</span><strong>${wpNumber(item.top10TitleCount)}</strong><small>고유 제목 기준</small></div>
        <div><span>총 노출</span><strong>${wpNumber(item.occurrenceCount)}</strong><small>5개 목록 합산</small></div>
      </div>
      <div class="weekly-pattern-detail-grid">
        <div class="weekly-representatives"><h4>대표 제목</h4><ol>${representatives}</ol></div>
        <div class="weekly-category-bars"><h4>카테고리 분포</h4>${categories}</div>
      </div>
      <div class="weekly-pattern-reason"><b>클릭 기대를 만드는 방식</b><p>${wpEscape(item.reason)}</p></div>
    </article>
  `;
}

function renderWeeklyControls() {
  const select = wp$('#weekly-pattern-select');
  if (!select) return;
  const reports = [...(weeklyState.index?.reports ?? [])].reverse();
  select.innerHTML = reports.map(item => `
    <option value="${wpEscape(item.key)}">${wpDate(item.startDate)} ~ ${wpDate(item.endDate)}</option>
  `).join('');
  select.value = weeklyState.key;
}

function renderWeeklyPatterns() {
  const report = weeklyState.report;
  if (!report) return;
  renderWeeklyControls();

  const quality = report.dataQuality ?? {};
  const qualityText = quality.complete
    ? `${quality.collectedDays}/${quality.expectedDays}일 전체 수집`
    : `${quality.collectedDays}/${quality.expectedDays}일 수집 · 누락 ${quality.missingDays?.join(', ') || '확인 필요'}`;
  wp$('#weekly-pattern-status').innerHTML = `
    <div class="weekly-alert ${quality.complete ? 'success' : 'warning'}">
      <b>${wpDate(report.startDate)} ~ ${wpDate(report.endDate)}</b>
      <span>${qualityText} · 전주 비교 ${wpDate(report.previousStartDate)} ~ ${wpDate(report.previousEndDate)} · 생성 ${wpDateTime(report.generatedAt)}</span>
    </div>
  `;

  wp$('#weekly-stat-titles').textContent = wpNumber(report.summary?.uniqueTitleCount);
  wp$('#weekly-stat-headline').textContent = report.headline || '—';
  wp$('#weekly-stat-patterns').textContent = wpNumber(report.patterns?.length);
  wp$('#weekly-stat-days').textContent = `${wpNumber(quality.collectedDays)}/${wpNumber(quality.expectedDays)}`;

  wp$('#weekly-highlights').innerHTML = (report.highlights ?? []).map(item => `<li>${wpEscape(item)}</li>`).join('');
  wp$('#weekly-rising').innerHTML = renderChangeList(report.risingPatterns, '뚜렷한 상승 패턴이 없습니다.');
  wp$('#weekly-falling').innerHTML = renderChangeList(report.fallingPatterns, '뚜렷한 약화 패턴이 없습니다.');
  wp$('#weekly-pattern-list').innerHTML = (report.patterns ?? []).map(renderPatternCard).join('');

  const newBest = report.newBest ?? {};
  wp$('#weekly-new-best-note').innerHTML = `
    <strong>${newBest.available ? '연결 가능한 신규베스트 데이터 있음' : '해당 기간 신규베스트 데이터 없음'}</strong>
    <p>${wpEscape(newBest.note || '신규베스트 수집 상태를 확인할 수 없습니다.')}</p>
    <small>신규베스트가 있는 주간부터는 TOP 20·50·100·200 진입과 초기 순위 상승폭을 함께 연결할 수 있습니다.</small>
  `;
  wp$('#weekly-conclusion').textContent = report.oneLineConclusion || '주간 결론을 준비 중입니다.';
  wp$('#weekly-watchlist').innerHTML = `
    <span>다음 주 관찰</span>
    ${(report.watchlist ?? []).map(item => `<b>${wpEscape(item)}</b>`).join('')}
  `;
  wp$('#weekly-method-note').textContent = report.methodNote || '';
}

function showWeeklyPatterns(active) {
  const view = wp$('#weekly-patterns-view');
  if (!view) return;
  view.hidden = !active;
  if (active) {
    wp$('#titles-view')?.setAttribute('hidden', '');
    wp$('#insights-view')?.setAttribute('hidden', '');
    wp$('#new-best-view')?.setAttribute('hidden', '');
    wp$$('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === 'weekly-patterns'));
    if (!weeklyState.loaded) loadWeeklyPatterns();
    if (weeklyState.report?.generatedAt && wp$('#updated-at')) {
      wp$('#updated-at').textContent = `주간 리포트 갱신 ${wpDateTime(weeklyState.report.generatedAt)}`;
    }
  }
}

function bindWeeklyEvents() {
  wp$$('.nav-button').forEach(button => {
    button.addEventListener('click', () => showWeeklyPatterns(button.dataset.view === 'weekly-patterns'));
  });
  wp$('#weekly-pattern-select')?.addEventListener('change', async event => {
    try {
      await loadWeeklyReport(event.target.value);
      renderWeeklyPatterns();
    } catch (error) {
      wp$('#weekly-pattern-status').innerHTML = `<div class="weekly-alert error">${wpEscape(error.message)}</div>`;
    }
  });
}

ensureWeeklySurface();
bindWeeklyEvents();
loadWeeklyPatterns();
