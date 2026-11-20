(function () {
  'use strict';
  var boton = document.getElementById('btn-push');
  if (!boton) return;
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    boton.disabled = true;
    boton.textContent = 'Este celular no admite notificaciones push';
    return;
  }
  function aBytes(b64) {
    var relleno = '='.repeat((4 - b64.length % 4) % 4);
    var crudo = atob((b64 + relleno).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(crudo, function (c) { return c.charCodeAt(0); });
  }
  boton.addEventListener('click', function () {
    Notification.requestPermission().then(function (permiso) {
      if (permiso !== 'granted') { window.alert('No se dio permiso para enviar avisos.'); return; }
      return navigator.serviceWorker.ready
        .then(function (reg) {
          return reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: aBytes(boton.dataset.clave)});
        })
        .then(function (sub) {
          var j = sub.toJSON();
          return fetch(boton.dataset.url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json',
                      'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
            body: JSON.stringify({endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth})
          });
        })
        .then(function (resp) {
          if (resp && resp.ok) boton.textContent = 'Notificaciones activadas ✓';
        });
    }).catch(function () { window.alert('No se pudieron activar las notificaciones.'); });
  });
})();