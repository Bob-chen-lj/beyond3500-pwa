var CACHE_NAME = 'beyond3500-v5';
var CORE_ASSETS = [
  '/',
  '/index.html',
  '/cards.js',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];
var IMG_CACHE_NAME = 'beyond3500-imgs-v1';

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(CORE_ASSETS);
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME && n !== IMG_CACHE_NAME; })
             .map(function(n) { return caches.delete(n); })
      );
    }).then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);
  
  // Cache Pollinations images separately
  if (url.hostname === 'image.pollinations.ai') {
    e.respondWith(
      caches.open(IMG_CACHE_NAME).then(function(cache) {
        return cache.match(e.request).then(function(cached) {
          if (cached) return cached;
          return fetch(e.request).then(function(resp) {
            if (resp.ok) {
              cache.put(e.request, resp.clone());
            }
            return resp;
          });
        });
      })
    );
    return;
  }
  
  // Default: cache-first for local assets
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
      if (e.request.mode === 'navigate') {
        return caches.match('/index.html');
      }
    })
  );
});
