import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.17.0/firebase-app.js';
import { getAnalytics, isSupported } from 'https://www.gstatic.com/firebasejs/12.17.0/firebase-analytics.js';

const firebaseConfig = {
  apiKey: 'AIzaSyDDKNjk3SASAHiii9WGzR1oa_ohgoaH9vg',
  authDomain: 'munpia-ranking.firebaseapp.com',
  projectId: 'munpia-ranking',
  storageBucket: 'munpia-ranking.firebasestorage.app',
  messagingSenderId: '426332760688',
  appId: '1:426332760688:web:2d4ff667bc2f399f3762b5',
  measurementId: 'G-61RNC94YBW'
};

async function initializeFirebaseAnalytics() {
  try {
    if (!(await isSupported())) {
      console.info('Firebase Analytics is not supported in this browser context.');
      return;
    }

    const app = initializeApp(firebaseConfig);
    getAnalytics(app);
    document.documentElement.dataset.firebaseAnalytics = 'enabled';
  } catch (error) {
    console.warn('Firebase Analytics initialization was skipped.', error);
  }
}

initializeFirebaseAnalytics();
