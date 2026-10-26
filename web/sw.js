// Offline cache: the app starts without a network once it has loaded one time.
//
// The app's own files are fetched from the network first, so a new version shows up on the
// next load, and come from the cache when offline. Both ask the server, never the browser's
// own HTTP cache, so a page never mixes files from two versions.
//
// Opening the app with ?fresh (see index.html) removes this worker and its caches. Pyodide, Pillow and qrcode come from
// versioned CDN addresses, so the cached copy is used first. build.py fills in the two values.

const BUILD = '__BUILD__';
const APP_FILES = __APP_FILES__;

const APP_CACHE = `app-${BUILD}`;
const RUNTIME_CACHE = 'runtime-v1';
const VERSIONED_HOSTS = ['cdn.jsdelivr.net', 'files.pythonhosted.org'];

self.addEventListener('install', (event) => {
  const requests = APP_FILES.map((file) => new Request(file, { cache: 'reload' }));
  event.waitUntil(caches.open(APP_CACHE).then((cache) => cache.addAll(requests)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith('app-') && name !== APP_CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request, { cache: 'no-cache' });
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok || response.type === 'opaque') cache.put(request, response.clone());
  return response;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  // Google sign-in (web/drive_auth.py) always goes to the server and is never cached
  if (url.origin === self.location.origin && url.pathname.startsWith('/auth/')) return;
  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(request, APP_CACHE));
  } else if (VERSIONED_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request));
  } else if (url.hostname === 'pypi.org') {
    event.respondWith(networkFirst(request, RUNTIME_CACHE));
  }
});
