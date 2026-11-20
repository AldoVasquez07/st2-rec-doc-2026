{% load static %}/* AgroPredix · Service Worker (RF-0015) · versión {{ version }}
 *
 * - Páginas de lectura (inicio, parcelas, recomendaciones): primero la red; si no hay señal, la última copia guardada.
 * - Archivos estáticos y Bootstrap: se guardan para abrir la app sin internet.
 * - Los envíos de formularios (POST) nunca se tocan: siempre van a la red.
 */
const VERSION = '{{ version }}';
const CACHE_BASE = `agropredix-base-${VERSION}`;   // archivos de la app: se renueva al cambiar la versión
const CACHE_PAGINAS = 'agropredix-paginas-v1';      // páginas visitadas: se conserva entre versiones
const MAX_PAGINAS = 40;
const ESPERA_RED_MS = 4000;                         // con señal mala, pasado este tiempo se usa la copia guardada
const URL_OFFLINE = '{% url "pwa:offline" %}';
const HOSTS_CDN = ['cdn.jsdelivr.net'];

// Si cambia la versión de Bootstrap en base.html, cambie también estas dos direcciones.
const PRECARGA = [
  URL_OFFLINE,
  '{% static "pwa/pwa.js" %}',
  '{% static "pwa/sincronizacion.js" %}',
  '{% static "pwa/icon-192.png" %}',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
];





// Solo se guardan páginas de lectura. Los formularios y el mapa necesitan internet.
const PAGINAS_GUARDABLES = [
  /^\/$/,
  /^\/parcelas\/$/,
  /^\/recomendaciones\/$/,
  /^\/recomendaciones\/\d+\/$/,
  /^\/clima\/parcela\/\d+\/$/,                  // clima: sin señal se ve el último dato guardado (RF-0010)
  /^\/parcelas\/\d+\/(historial|suelo)\/$/,     // se pueden abrir sin señal para registrar datos (se sincronizan al volver)
];

const esGuardable = (url) => url.origin === self.location.origin &&
  PAGINAS_GUARDABLES.some((patron) => patron.test(url.pathname));

// 200 directa (ni redirecciones ni errores): así no se guarda la pantalla de ingreso por equivocación
const respuestaValida = (resp) => resp && resp.status === 200 && resp.type === 'basic' && !resp.redirected;

async function guardarPagina(request, resp) {
  const cache = await caches.open(CACHE_PAGINAS);
  await cache.put(request, resp);
  const claves = await cache.keys();
  for (let i = 0; i < claves.length - MAX_PAGINAS; i++) await cache.delete(claves[i]);   // las más viejas primero
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_BASE);
    await Promise.all(PRECARGA.map(async (direccion) => {
      try {
        const propia = direccion.startsWith('/');
        const pedido = new Request(direccion, {mode: propia ? 'same-origin' : 'no-cors'});
        const resp = await fetch(pedido);
        if (resp.ok || resp.type === 'opaque') await cache.put(pedido, resp);
      } catch (_) { /* un archivo que falle no debe impedir la instalación */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const nombres = await caches.keys();
    await Promise.all(nombres
      .filter((n) => n.startsWith('agropredix-base-') && n !== CACHE_BASE)
      .map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

function conTiempo(promesa, ms) {
  return new Promise((resolver, rechazar) => {
    const reloj = setTimeout(() => rechazar(new Error('tiempo agotado')), ms);
    promesa.then((r) => { clearTimeout(reloj); resolver(r); }, (e) => { clearTimeout(reloj); rechazar(e); });
  });
}

async function paginaRedPrimero(event) {
  const request = event.request;
  const url = new URL(request.url);
  const guardable = esGuardable(url);
  const guardada = guardable ? await caches.match(request, {cacheName: CACHE_PAGINAS, ignoreVary: true}) : undefined;

  // La petición sigue su curso aunque se agote la espera, y al terminar renueva la copia guardada
  const red = fetch(request).then(async (resp) => {
    if (guardable && respuestaValida(resp)) await guardarPagina(request, resp.clone());
    return resp;
  });
  event.waitUntil(red.catch(() => {}));

  try {
    const resp = await (guardada ? conTiempo(red, ESPERA_RED_MS) : red);
    if (resp.status >= 500 && guardada) return guardada;       // el servidor falló: mejor la última copia buena
    return resp;
  } catch (_) {
    if (guardada) return guardada;
    const aviso = await caches.match(URL_OFFLINE, {cacheName: CACHE_BASE});
    return aviso || Response.error();
  }
}

async function estaticoConActualizacion(event) {
  const cache = await caches.open(CACHE_BASE);
  const guardado = await cache.match(event.request);
  const actualizado = fetch(event.request).then((resp) => {
    if (resp.ok) cache.put(event.request, resp.clone());
    return resp;
  }).catch(() => null);
  if (guardado) { event.waitUntil(actualizado); return guardado; }
  return (await actualizado) || Response.error();
}

async function cdnPrimeroCache(event) {
  const cache = await caches.open(CACHE_BASE);
  const guardado = await cache.match(event.request);
  if (guardado) return guardado;
  try {
    const resp = await fetch(event.request);
    if (resp.ok || resp.type === 'opaque') cache.put(event.request, resp.clone());
    return resp;
  } catch (_) {
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;                       // formularios y envíos: directo a la red
  const url = new URL(request.url);

  if (url.origin === self.location.origin) {
    if (url.pathname.startsWith('/static/')) { event.respondWith(estaticoConActualizacion(event)); return; }
    if (request.mode === 'navigate') { event.respondWith(paginaRedPrimero(event)); }
    return;                                                   // todo lo demás, a la red sin intervenir
  }
  if (HOSTS_CDN.includes(url.hostname)) event.respondWith(cdnPrimeroCache(event));
});

// Mensajes de la página: precargar las últimas recomendaciones y limpiar al cerrar sesión
self.addEventListener('message', (event) => {
  const datos = event.data || {};
  if (datos.tipo === 'PRECARGAR' && Array.isArray(datos.urls)) {
    event.waitUntil(Promise.all(datos.urls.map(async (direccion) => {
      try {
        const url = new URL(direccion, self.location.origin);
        if (!esGuardable(url)) return;
        const request = new Request(url.href, {credentials: 'same-origin'});
        const resp = await fetch(request);
        if (respuestaValida(resp)) await guardarPagina(request, resp);
      } catch (_) { /* sin señal: se intentará en la próxima visita */ }
    })));
  }
  if (datos.tipo === 'LIMPIAR') event.waitUntil(caches.delete(CACHE_PAGINAS));
});