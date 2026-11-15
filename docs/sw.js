// Rede primeiro; sem internet, mostra a última versão guardada.
importScripts('avisos.js');
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

// Avisos de estreia com o app fechado (o navegador decide quando rodar; só em app instalado).
self.addEventListener('periodicsync', e => {
  if (e.tag === 'avisos') e.waitUntil(avisarEmSegundoPlano());
});
async function avisarEmSegundoPlano() {
  const d = await (await fetch('data/dados.json', { cache: 'no-store' })).json();
  await dispararAvisos([...Object.values(d.series), ...Object.values(d.filmes)], dataLocal(),
    p => self.registration.showNotification(p.titulo, { body: p.corpo, tag: p.chave, icon: 'icon-192.png' }));
}

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window' }).then(abertas => abertas.length ? abertas[0].focus() : self.clients.openWindow('./')));
});
