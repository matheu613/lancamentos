// Rede primeiro; sem internet, mostra a última versão guardada.
const CACHE = 'lancamentos-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.includes('/api/')) return;
  e.respondWith(
    fetch(e.request, { cache: 'no-store' })
      .then(resp => {
        if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        return resp;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || Response.error()))
  );
});
