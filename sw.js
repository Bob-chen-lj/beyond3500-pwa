var CACHE_NAME = 'beyond3500-v2';
var ASSETS = [
  '/',
  '/index.html',
  '/cards.js',
  '/waud.js',
  '/eaud.js',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      // Cache core files first (cards.js is tiny, waud/eaud are big - cache in background)
      return cache.addAll(['/', '/index.html', '/cards.js', '/manifest.json', '/icon-192.png', '/icon-512.png']);
    }).then(function() {
      // Cache large audio files in background
      return caches.open(CACHE_NAME).then(function(cache) {
        return Promise.allSettled([
          cache.add('/waud.js'),
          cache.add('/eaud.js')
        ]);
      });
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME; })
             .map(function(n) { return caches.delete(n); })
      );
    }).then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(e) {
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request).then(function(resp) {
        if (resp.ok) {
          var clone = resp.clone();
          caches.open(CACHE_NAME).then(function(cache) { cache.put(e.request, clone); });
        }
        return resp;
      });
    }).catch(function() {
      // Offline fallback for navigation
      if (e.request.mode === 'navigate') {
        return caches.match('/index.html');
      }
    })
  );
});
