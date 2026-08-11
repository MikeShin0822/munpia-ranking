(() => {
  const nativeFetch = window.fetch.bind(window);
  const rawRoot = 'https://raw.githubusercontent.com/MikeShin0822/munpia-ranking/main';

  window.fetch = async (input, init = {}) => {
    const requestedUrl = typeof input === 'string' ? input : input.url;
    const resolvedUrl = new URL(requestedUrl, window.location.href);
    const rankingMatch = resolvedUrl.pathname.endsWith('/data/rankings.json');
    const newBestMarker = '/data/new-best/';
    const newBestIndex = resolvedUrl.pathname.indexOf(newBestMarker);
    const isNewBestData = newBestIndex >= 0;

    if ((rankingMatch || isNewBestData) && window.location.hostname.endsWith('github.io')) {
      try {
        const remoteUrl = rankingMatch
          ? `${rawRoot}/data/rankings.json`
          : `${rawRoot}${resolvedUrl.pathname.slice(newBestIndex)}`;
        const response = await nativeFetch(`${remoteUrl}?v=${Date.now()}`, {
          ...init,
          cache: 'no-store'
        });
        if (response.ok) return response;
      } catch (error) {
        console.warn('최신 원격 데이터를 불러오지 못해 배포본 데이터로 대체합니다.', error);
      }
    }

    return nativeFetch(input, init);
  };

  void import(new URL('./firebase-analytics.js', document.baseURI).href).catch(error => {
    console.warn('Firebase Analytics 모듈을 불러오지 못했습니다.', error);
  });
})();
