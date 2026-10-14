// Firebase Cloud Messaging: shows Kaarigar alerts even when the app is closed.
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');
firebase.initializeApp({
  apiKey: "AIzaSyCtBfoI2roXMXa-8dHGofdgPijgBDMlwT0", authDomain: "kaarigar-510716.firebaseapp.com",
  projectId: "kaarigar-510716", storageBucket: "kaarigar-510716.firebasestorage.app",
  messagingSenderId: "1092998207528", appId: "1:1092998207528:web:5441cbf174d6987d0efd1d"
});
firebase.messaging().onBackgroundMessage(p => {
  const d = p.data || {};
  self.registration.showNotification(d.title || 'Kaarigar', {
    body: d.body || '', icon: '/icon-192.png', badge: '/icon-192.png',
    tag: d.tag || 'kaarigar', requireInteraction: true, data: { url: d.url || '/' } });
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow((e.notification.data && e.notification.data.url) || '/'));
});
