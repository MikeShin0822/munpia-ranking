(() => {
  const nativeFetch = window.fetch.bind(window);
  const liveDataUrl = 'https://raw.githubusercontent.com/MikeShin0822/munpia-ranking/main/data/rankings.json';

  window.fetch = async (input, init = {}) => {
    const requestedUrl = typeof input === 'string' ? input : input.url;
    const resolvedUrl = new URL(requestedUrl, window.location.href);
    const isRankingData = resolvedUrl.pathname.endsWith('/data/rankings.json');

    if (isRankingData && window.location.hostname.endsWith('github.io')) {
      try {
        const response = await nativeFetch(`${liveDataUrl}?v=${Date.now()}`, {
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
})();
