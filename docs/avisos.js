// Lista de desejos e avisos de estreia. Compartilhado entre a página e o service worker.
// O estado fica no aparelho: { desejos: {id: dataEmQueMarcou}, avisados: {chave: dataDoAviso} }.
const ESTADO_CACHE = 'lancamentos-estado';
const ESTADO_URL = 'estado.json';

function dataLocal(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function maisDias(iso, n) {
  const [a, m, d] = iso.split('-').map(Number);
  return dataLocal(new Date(a, m - 1, d + n));
}

async function lerEstado() {
  try {
    let bruto = null;
    if (self.caches) {  // visível também para o service worker
      const r = await (await caches.open(ESTADO_CACHE)).match(ESTADO_URL);
      bruto = r ? await r.json() : null;
    } else if (self.localStorage) {
      bruto = JSON.parse(localStorage.getItem('estado'));
    }
    if (bruto) return { desejos: bruto.desejos || {}, avisados: bruto.avisados || {} };
  } catch (e) {}
  return { desejos: {}, avisados: {} };
}
async function gravarEstado(estado) {
  try {
    const texto = JSON.stringify(estado);
    if (self.caches) await (await caches.open(ESTADO_CACHE)).put(ESTADO_URL, new Response(texto, { headers: { 'Content-Type': 'application/json' } }));
    else if (self.localStorage) localStorage.setItem('estado', texto);
  } catch (e) {}
}

// Texto de um aviso: quando = 'vespera' ou 'dia'.
function textoAviso(item, quando) {
  return {
    chave: `${item.id}-${quando}-${item.data}`,
    titulo: `${quando === 'dia' ? 'Estreia hoje' : 'Estreia amanhã'}: ${item.titulo}`,
    corpo: item.plataforma
      ? `${item.temporada > 1 ? `Temporada ${item.temporada}` : 'Série nova'} · ${item.plataforma}`
      : 'Filme nos cinemas',
  };
}

// Avisos que ainda não foram mostrados: um na véspera e um no dia da estreia de cada desejo.
function avisosPendentes(estado, itens, hoje) {
  const amanha = maisDias(hoje, 1);
  const pendentes = [];
  for (const item of itens) {
    if (!(item.id in estado.desejos)) continue;
    const quando = item.data === hoje ? 'dia' : item.data === amanha ? 'vespera' : null;
    if (!quando) continue;
    const aviso = textoAviso(item, quando);
    if (!estado.avisados[aviso.chave]) pendentes.push(aviso);
  }
  return pendentes;
}

async function dispararAvisos(itens, hoje, mostrar) {
  const estado = await lerEstado();
  const pendentes = avisosPendentes(estado, itens, hoje);
  if (!pendentes.length) return 0;
  for (const p of pendentes) {
    try { await mostrar(p); estado.avisados[p.chave] = hoje; } catch (e) {}
  }
  const limite = maisDias(hoje, -10);
  for (const [chave, dia] of Object.entries(estado.avisados)) if (dia < limite) delete estado.avisados[chave];
  await gravarEstado(estado);
  return pendentes.length;
}
