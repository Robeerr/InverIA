// InverIA Service Worker — cache static assets, stale-while-revalidate for HTML
// v3: al añadir los iconos cambió el index.html. Subir la versión invalida la caché vieja
// (el handler de activate borra las que no coincidan) para que la pestaña coja el favicon
// sin esperar a que caduque el HTML cacheado.
const CACHE = 'inveria-v3';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip cross-origin (API calls to Render, Google Fonts network calls, etc.)
  if (url.origin !== self.location.origin) return;

  // Cache-first for hashed static assets (CRA adds content hash to filenames)
  if (/\.(js|css|woff2?|ttf|otf|png|svg|ico|webp|jpg|jpeg)(\?.*)?$/.test(url.pathname)) {
    e.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((res) => {
            if (res.ok) {
              const clone = res.clone();
              caches.open(CACHE).then((c) => c.put(request, clone));
            }
            return res;
          })
      )
    );
    return;
  }

  // Stale-while-revalidate for HTML shell — shows instantly, updates in background
  if (request.mode === 'navigate') {
    e.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((res) => {
            if (res.ok) {
              const clone = res.clone();
              caches.open(CACHE).then((c) => c.put(request, clone));
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
