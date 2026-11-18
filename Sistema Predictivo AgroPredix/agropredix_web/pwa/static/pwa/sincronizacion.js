/* AgroPredix · registros sin conexión (RF-0015 · CP-016)
 *
 * Los formularios marcados con data-pwa-form (historial y análisis de suelo) no se envían directo:
 * cada registro recibe un identificador único, se guarda en el celular (IndexedDB) y se manda al servidor.
 * Si no hay señal queda pendiente y se envía solo cuando vuelve la conexión. El servidor ignora los
 * identificadores que ya recibió, así que un reintento nunca duplica el registro. */
(function () {
  'use strict';
  if (!window.indexedDB || !window.fetch) return;          // navegador muy antiguo: los formularios funcionan como siempre

  var BD = 'agropredix', ALMACEN = 'pendientes', URL_SYNC = '/parcelas/sincronizar/';
  var usuario = document.body.getAttribute('data-usuario') || '';
  var ocupado = false;

  // ---------- cola en el celular (IndexedDB) ----------
  function abrirBD() {
    return new Promise(function (ok, fallo) {
      var pedido = indexedDB.open(BD, 1);
      pedido.onupgradeneeded = function () { pedido.result.createObjectStore(ALMACEN, {keyPath: 'uuid'}); };
      pedido.onsuccess = function () { ok(pedido.result); };
      pedido.onerror = function () { fallo(pedido.error); };
    });
  }
  function operar(modo, accion) {
    return abrirBD().then(function (bd) {
      return new Promise(function (ok, fallo) {
        var t = bd.transaction(ALMACEN, modo);
        var pedido = accion(t.objectStore(ALMACEN));
        t.oncomplete = function () { bd.close(); ok(pedido ? pedido.result : undefined); };
        t.onerror = t.onabort = function () { bd.close(); fallo(t.error); };
      });
    });
  }
  function guardar(item) { return operar('readwrite', function (s) { return s.put(item); }); }
  function quitar(id) { return operar('readwrite', function (s) { return s.delete(id); }); }
  function todos() {
    return operar('readonly', function (s) { return s.getAll(); }).then(function (lista) {
      return (lista || []).filter(function (i) { return i.usuario === usuario; })    // cada usuario ve solo lo suyo
        .sort(function (a, b) { return a.creado - b.creado; });
    });
  }

  // ---------- utilidades ----------
  function nuevoUUID() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
    return [h.slice(0, 8), h.slice(8, 12), h.slice(12, 16), h.slice(16, 20), h.slice(20)].join('-');
  }
  function tokenCSRF() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
  }
  function leerFormulario(form) {
    var datos = {}, resumen = [];
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name === 'csrfmiddlewaretoken' || el.disabled || el.type === 'submit' || el.type === 'button') return;
      datos[el.name] = el.value;
      if (el.value === '') return;
      var etiqueta = form.querySelector('label[for="' + el.id + '"]');
      var texto = el.tagName === 'SELECT' ? el.options[el.selectedIndex].text : el.value;
      resumen.push((etiqueta ? etiqueta.textContent.trim().replace(/[:*\s]+$/, '') + ': ' : '') + texto);
    });
    return {datos: datos, resumen: resumen.join(' · ')};
  }

  // ---------- avisos en pantalla ----------
  function contenedorAvisos() {
    var c = document.getElementById('pwa-avisos');
    if (!c) {
      c = document.createElement('div');
      c.id = 'pwa-avisos';
      c.style.cssText = 'position:fixed;left:8px;right:8px;bottom:92px;z-index:2100;max-width:480px;margin:0 auto';
      document.body.appendChild(c);
    }
    return c;
  }
  function aviso(texto, tipo, boton) {
    var caja = document.createElement('div');
    caja.className = 'alert alert-' + (tipo || 'info') + ' shadow small py-2 mb-2';
    caja.setAttribute('role', 'status');
    caja.appendChild(document.createTextNode(texto + ' '));
    if (boton) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'btn btn-sm btn-outline-dark ms-2'; b.textContent = boton.texto;
      b.addEventListener('click', boton.accion);
      caja.appendChild(b);
    }
    contenedorAvisos().appendChild(caja);
    setTimeout(function () { if (caja.parentNode) caja.parentNode.removeChild(caja); }, boton ? 15000 : 6000);
  }
  function limpiarErrores(form) {
    var previo = form.querySelector('[data-pwa-errores]');
    if (previo) previo.parentNode.removeChild(previo);
  }
  function mostrarErrores(form, errores) {
    limpiarErrores(form);
    var caja = document.createElement('div');
    caja.className = 'alert alert-danger small';
    caja.setAttribute('data-pwa-errores', '');
    (errores || ['No se pudo guardar.']).forEach(function (e) {
      var linea = document.createElement('div'); linea.textContent = e; caja.appendChild(linea);
    });
    form.insertBefore(caja, form.firstChild);
  }

  // indicador fijo "n registros sin enviar" y lista de pendientes dentro de cada pantalla
  var pastilla = document.createElement('div');
  pastilla.className = 'badge bg-warning text-dark shadow';
  pastilla.style.cssText = 'position:fixed;right:8px;bottom:50px;z-index:2000;display:none;font-size:.8rem';
  document.body.appendChild(pastilla);

  function actualizarIndicadores() {
    return todos().then(function (items) {
      pastilla.style.display = items.length ? 'block' : 'none';
      pastilla.textContent = items.length + (items.length === 1 ? ' registro sin enviar' : ' registros sin enviar');
      Array.prototype.forEach.call(document.querySelectorAll('[data-pwa-pendientes]'), function (panel) {
        var propios = items.filter(function (i) {
          return i.tipo === panel.getAttribute('data-tipo') && String(i.parcela) === panel.getAttribute('data-parcela');
        });
        panel.textContent = '';
        if (!propios.length) return;
        var titulo = document.createElement('h6'); titulo.textContent = 'Pendientes de enviar'; panel.appendChild(titulo);
        propios.forEach(function (item) {
          var caja = document.createElement('div');
          caja.className = 'card mb-2 border-' + (item.estado === 'error' ? 'danger' : 'warning');
          var cuerpo = document.createElement('div');
          cuerpo.className = 'card-body py-2 d-flex justify-content-between align-items-center small';
          var texto = document.createElement('div');
          texto.textContent = item.resumen + (item.estado === 'error'
            ? ' — No se pudo guardar: ' + item.mensaje : ' — se enviará cuando haya señal');
          cuerpo.appendChild(texto);
          if (item.estado === 'error') {
            var b = document.createElement('button');
            b.type = 'button'; b.className = 'btn btn-outline-danger btn-sm'; b.textContent = 'Descartar';
            b.addEventListener('click', function () { quitar(item.uuid).then(actualizarIndicadores); });
            cuerpo.appendChild(b);
          }
          caja.appendChild(cuerpo); panel.appendChild(caja);
        });
      });
    }).catch(function () {});
  }

  // ---------- envío al servidor ----------
  function enviar(item) {
    return fetch(URL_SYNC, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': tokenCSRF()},
      body: JSON.stringify({tipo: item.tipo, uuid: item.uuid, parcela: item.parcela, datos: item.datos}),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (cuerpo) {
        if (r.status === 401 || r.status === 403) return {resultado: 'sin_sesion'};
        if (r.ok) return {resultado: cuerpo.estado === 'duplicado' ? 'duplicado' : 'ok'};
        if (r.status >= 400 && r.status < 500) return {resultado: 'invalido', errores: cuerpo.errores};
        return {resultado: 'servidor'};
      });
    }, function () { return {resultado: 'sin_red'}; });
  }

  // Envía en orden todo lo pendiente. Se detiene si no hay señal o la sesión venció, y reintenta después.
  function sincronizar() {
    if (ocupado || !navigator.onLine || !usuario) return Promise.resolve(0);
    ocupado = true;
    var enviados = 0;
    return todos().then(function (items) {
      return items.filter(function (i) { return i.estado !== 'error'; }).reduce(function (cadena, item) {
        return cadena.then(function (seguir) {
          if (!seguir) return false;
          return enviar(item).then(function (r) {
            if (r.resultado === 'ok' || r.resultado === 'duplicado') { enviados++; return quitar(item.uuid).then(function () { return true; }); }
            if (r.resultado === 'invalido') {
              item.estado = 'error'; item.mensaje = (r.errores || ['Datos no válidos.']).join(' ');
              return guardar(item).then(function () { return true; });
            }
            return false;                                  // sin señal, servidor caído o sesión vencida
          });
        });
      }, Promise.resolve(true));
    }).catch(function () {}).then(function () {
      ocupado = false;
      return actualizarIndicadores();
    }).then(function () {
      if (enviados) {
        aviso('Se enviaron ' + enviados + (enviados === 1 ? ' registro' : ' registros') + ' que estaban pendientes.', 'success',
          {texto: 'Actualizar página', accion: function () { window.location.reload(); }});
      }
      return enviados;
    });
  }

  // ---------- formularios ----------
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.getAttribute || form.hasAttribute('data-pwa-salir')) return;
    var tipo = form.getAttribute('data-pwa-form');

    if (!tipo) {                                           // cualquier otro envío necesita internet
      if (!navigator.onLine && String(form.method).toLowerCase() === 'post') {
        e.preventDefault();
        aviso('Sin conexión: esta acción necesita internet.', 'warning');
      }
      return;
    }
    if (!usuario) return;                                  // sin sesión: se deja el envío normal
    e.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    if (form.getAttribute('data-enviando')) return;        // evita el doble toque
    form.setAttribute('data-enviando', '1');
    limpiarErrores(form);

    var leido = leerFormulario(form);
    var item = {uuid: nuevoUUID(), tipo: tipo, parcela: Number(form.getAttribute('data-parcela')), usuario: usuario,
                datos: leido.datos, resumen: leido.resumen, creado: Date.now(), estado: 'pendiente', mensaje: ''};

    guardar(item)                                          // primero queda a salvo en el celular
      .then(function () { return enviar(item); })
      .then(function (r) {
        if (r.resultado === 'ok' || r.resultado === 'duplicado') {
          return quitar(item.uuid).then(function () {
            aviso('Guardado.', 'success');
            setTimeout(function () { window.location.reload(); }, 600);
          });
        }
        if (r.resultado === 'invalido') {                  // se queda el formulario para corregirlo
          return quitar(item.uuid).then(function () { mostrarErrores(form, r.errores); });
        }
        form.reset();                                      // sin señal / servidor caído / sesión vencida: queda pendiente
        aviso(r.resultado === 'sin_sesion'
          ? 'Su sesión venció. Ingrese de nuevo y sus registros se enviarán.'
          : 'Guardado en su celular. Se enviará cuando tenga señal.', r.resultado === 'sin_sesion' ? 'warning' : 'success');
      })
      .catch(function () { aviso('No se pudo guardar en el celular. Inténtelo de nuevo.', 'danger'); })
      .then(function () { form.removeAttribute('data-enviando'); return actualizarIndicadores(); });
  });

  // ---------- cuándo se intenta enviar ----------
  window.addEventListener('online', sincronizar);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') sincronizar(); });
  setInterval(sincronizar, 60000);                         // por si la señal vuelve con la pantalla abierta
  setTimeout(function () { actualizarIndicadores().then(sincronizar); }, 1000);

  window.AgroPredixCola = {
    sincronizar: sincronizar,
    contar: function () { return todos().then(function (l) { return l.length; }, function () { return 0; }); },
  };
})();