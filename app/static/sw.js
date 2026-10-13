// Minimal service worker: makes Kaarigar installable. No caching, so users always get fresh results.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
