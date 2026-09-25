/**
 * Larsson Market Scanner Service Worker (PWA)
 * - Cache-first strategy for static assets (index.html, app.js, style.css, icons)
 * - Network-first strategy for dynamic data (/data.json, /api/)
 * - Offline fallback with cached data and status signaling
 */

const CACHE_NAME = 'larsson-v1';
const STATIC_ASSETS = [
  './',
  'index.html',
  'app.js',
  'style.css',
  'manifest.json',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-192.svg',
  'icons/icon-512.svg'
];

// Install: precache static assets
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Caching static assets');
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Pre-caching warning:', err);
      });
    })
  );
});

// Activate: clean up outdated caches and take control
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Removing old cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-first for data/API, Cache-first for static assets
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') {
    return;
  }

  const url = new URL(req.url);

  // Dynamic endpoints: /data.json or /api/
  const isDataRequest = url.pathname.endsWith('data.json') || url.pathname.includes('/api/');

  if (isDataRequest) {
    event.respondWith(
      fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(req, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(async () => {
          console.log('[SW] Network failed, serving cached dynamic data:', req.url);
          const cachedResponse = await caches.match(req);
          if (cachedResponse) {
            return cachedResponse;
          }
          // Fallback if data.json was never cached
          if (url.pathname.endsWith('data.json')) {
            return new Response(
              JSON.stringify({ symbols: [], summary: {}, offline: true }),
              { headers: { 'Content-Type': 'application/json' } }
            );
          }
          return new Response('Offline', { status: 503, statusText: 'Offline' });
        })
    );
    return;
  }

  // Static assets: Cache-first with network fallback & background cache update
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      if (cachedResponse) {
        // Fetch in background to update cache for subsequent visits
        fetch(req)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(req, networkResponse);
              });
            }
          })
          .catch(() => {});
        return cachedResponse;
      }

      return fetch(req).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(req, responseClone);
          });
        }
        return networkResponse;
      });
    })
  );
});
