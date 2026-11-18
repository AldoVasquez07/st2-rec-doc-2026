/* AgroPredix · cliente PWA (RF-0015): registro del service worker, aviso sin conexión,
 * botón "Instalar app" y precarga de las últimas recomendaciones. */
(function () {
  'use strict';

  // 1) Registrar el service worker (se sirve desde la raíz para controlar todo el sitio)
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/service-worker.js', {scope: '/'})
        .then(precargarRecomendaciones)
        .catch(function (e) { console.warn('No se pudo registrar el service worker', e); });
    });
  }

  // 2) Aviso de "sin conexión"
  var aviso = document.createElement('div');
  aviso.setAttribute('role', 'status');
  aviso.className = 'alert alert-warning text-center mb-0 rounded-0 py-2 small';
  aviso.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2000;display:none';
  aviso.textContent = 'Sin conexión: está viendo lo último que se guardó en su celular.';
  document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(aviso); actualizarAviso(); });
  function actualizarAviso() { aviso.style.display = navigator.onLine ? 'none' : 'block'; }
  window.addEventListener('online', actualizarAviso);
  window.addEventListener('offline', actualizarAviso);

  // 3) Botón "Instalar app" (Chrome/Android avisa cuando la app se puede instalar)
  var ofertaInstalar = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    ofertaInstalar = e;
    var boton = document.getElementById('btn-instalar');
    if (boton) boton.classList.remove('d-none');
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest || !e.target.closest('#btn-instalar') || !ofertaInstalar) return;
    ofertaInstalar.prompt();
    ofertaInstalar.userChoice.finally(function () {
      ofertaInstalar = null;
      var boton = document.getElementById('btn-instalar');
      if (boton) boton.classList.add('d-none');
    });
  });
  window.addEventListener('appinstalled', function () {
    var boton = document.getElementById('btn-instalar');
    if (boton) boton.classList.add('d-none');
  });

  // 4) Guardar para uso sin señal las recomendaciones marcadas con data-pwa-precargar
  function precargarRecomendaciones() {
    var enlaces = document.querySelectorAll('a[data-pwa-precargar]');
    if (!enlaces.length || !navigator.onLine) return;
    var urls = Array.prototype.map.call(enlaces, function (a) { return a.getAttribute('href'); });
    navigator.serviceWorker.ready.then(function (registro) {
      if (registro.active) registro.active.postMessage({tipo: 'PRECARGAR', urls: urls});
    });
  }

  // 5) Al cerrar sesión se borran las páginas guardadas (en un celular compartido no deben quedar datos)
  function contarPendientes() {
    var cola = window.AgroPredixCola;
    return cola ? cola.contar().catch(function () { return 0; }) : Promise.resolve(0);
  }
  function borrarPaginasGuardadas() {
    if (!('caches' in window)) return Promise.resolve();
    return caches.keys()
      .then(function (nombres) {
        return Promise.all(nombres.filter(function (n) { return n.indexOf('agropredix-paginas') === 0; })
          .map(function (n) { return caches.delete(n); }));
      })
      .catch(function () {});
  }
  document.addEventListener('submit', function (e) {
    var formulario = e.target;
    if (!formulario.hasAttribute || !formulario.hasAttribute('data-pwa-salir')) return;
    e.preventDefault();
    if (!navigator.onLine) { window.alert('Sin conexión: para cerrar sesión necesita internet.'); return; }
    contarPendientes().then(function (n) {
      if (n > 0 && !window.confirm('Tiene ' + n + (n === 1 ? ' registro' : ' registros') +
          ' sin enviar. Se enviarán cuando vuelva a ingresar con señal. ¿Cerrar sesión de todos modos?')) return;
      return borrarPaginasGuardadas().then(function () { formulario.submit(); });
    });
  });
})();