const FIREBASE_VERSION = '12.17.0';
const MEASUREMENT_ID = 'G-61RNC94YBW';

const firebaseConfig = {
  apiKey: 'AIzaSyDDKNjk3SASAHiii9WGzR1oa_ohgoaH9vg',
  authDomain: 'munpia-ranking.firebaseapp.com',
  projectId: 'munpia-ranking',
  storageBucket: 'munpia-ranking.firebasestorage.app',
  messagingSenderId: '426332760688',
  appId: '1:426332760688:web:2d4ff667bc2f399f3762b5',
  measurementId: MEASUREMENT_ID
};

const debugMode = new URLSearchParams(window.location.search).get('firebase_debug') === '1';

function eventParams(extra = {}) {
  return {
    app_surface: 'github_pages',
    ...extra,
    ...(debugMode ? { debug_mode: true } : {})
  };
}

function setStatus(status, detail = '') {
  document.documentElement.dataset.firebaseAnalytics = status;
  window.munpiaAnalyticsStatus = { status, detail, debugMode };
  console.info(`[Analytics] ${status}${detail ? `: ${detail}` : ''}`);
}

async function createFirebaseSender() {
  const [{ initializeApp }, analyticsModule] = await Promise.all([
    import(`https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-app.js`),
    import(`https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-analytics.js`)
  ]);

  if (!(await analyticsModule.isSupported())) {
    throw new Error('Firebase Analytics is not supported in this browser context.');
  }

  const app = initializeApp(firebaseConfig);
  const analytics = analyticsModule.initializeAnalytics(app, {
    config: {
      send_page_view: false,
      page_title: document.title,
      page_location: window.location.href
    }
  });

  return {
    source: 'firebase_sdk',
    send(name, params = {}) {
      analyticsModule.logEvent(analytics, name, eventParams(params));
    }
  };
}

function createGtagFallback(reason) {
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function gtag() {
    window.dataLayer.push(arguments);
  };

  const scriptId = 'munpia-google-tag';
  if (!document.getElementById(scriptId)) {
    const script = document.createElement('script');
    script.id = scriptId;
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
    script.onerror = () => setStatus('blocked', 'Google tag request failed or was blocked.');
    document.head.appendChild(script);
  }

  window.gtag('js', new Date());
  window.gtag('config', MEASUREMENT_ID, {
    send_page_view: false,
    page_title: document.title,
    page_location: window.location.href,
    ...(debugMode ? { debug_mode: true } : {})
  });

  return {
    source: 'gtag_fallback',
    reason,
    send(name, params = {}) {
      window.gtag('event', name, eventParams(params));
    }
  };
}

async function initializeAnalyticsTracking() {
  let sender;

  try {
    sender = await createFirebaseSender();
    setStatus('firebase_sdk');
  } catch (error) {
    console.warn('[Analytics] Firebase SDK initialization failed. Using Google tag fallback.', error);
    sender = createGtagFallback(error instanceof Error ? error.message : String(error));
    setStatus('gtag_fallback', sender.reason);
  }

  sender.send('page_view', {
    page_title: document.title,
    page_location: window.location.href,
    page_path: window.location.pathname
  });

  sender.send('site_loaded', {
    analytics_source: sender.source,
    site_name: 'munpia_title_radar'
  });

  window.munpiaAnalytics = {
    source: sender.source,
    log(name, params = {}) {
      sender.send(name, params);
    }
  };
}

void initializeAnalyticsTracking();
