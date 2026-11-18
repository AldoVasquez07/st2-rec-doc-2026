import json
import struct

from django.contrib.staticfiles import finders
from django.test import override_settings
from django.urls import reverse

from usuarios.base_pruebas import PruebaBase


def tamano_png(ruta):
    """Ancho y alto de un PNG leyendo su cabecera (sin depender de Pillow)."""
    with open(ruta, 'rb') as f:
        cabecera = f.read(24)
    assert cabecera[:8] == b'\x89PNG\r\n\x1a\n', 'no es un PNG'
    return struct.unpack('>II', cabecera[16:24])


class ManifiestoTests(PruebaBase):
    def setUp(self):
        self.r = self.client.get('/manifest.webmanifest')
        self.datos = json.loads(self.r.content)

    def test_se_sirve_con_el_tipo_correcto_sin_iniciar_sesion(self):
        self.assertEqual(self.r.status_code, 200)
        self.assertEqual(self.r['Content-Type'], 'application/manifest+json')

    def test_campos_que_exige_chrome_para_instalar(self):
        d = self.datos
        self.assertEqual(d['display'], 'standalone')
        self.assertTrue(d['name'] and d['short_name'])
        self.assertEqual(d['start_url'], '/')
        self.assertEqual(d['scope'], '/')
        self.assertTrue(d['theme_color'].startswith('#'))

    def test_tiene_iconos_192_512_y_maskable(self):
        tamanos = {i['sizes'] for i in self.datos['icons']}
        self.assertTrue({'192x192', '512x512'} <= tamanos)
        self.assertIn('maskable', {i['purpose'] for i in self.datos['icons']})

    def test_los_iconos_existen_y_miden_lo_que_dicen(self):
        for icono in self.datos['icons']:
            ruta = finders.find(icono['src'].replace('/static/', '', 1))
            self.assertIsNotNone(ruta, icono['src'])
            ancho, alto = (int(n) for n in icono['sizes'].split('x'))
            self.assertEqual(tamano_png(ruta), (ancho, alto), icono['src'])

    def test_iconos_de_navegador_y_ios(self):
        for nombre in ('favicon.png', 'apple-touch-icon.png'):
            self.assertIsNotNone(finders.find('pwa/' + nombre), nombre)


class ServiceWorkerTests(PruebaBase):
    def test_se_sirve_desde_la_raiz_como_javascript(self):
        r = self.client.get('/service-worker.js')
        self.assertEqual(r.status_code, 200)
        self.assertIn('javascript', r['Content-Type'])
        self.assertEqual(r['Service-Worker-Allowed'], '/')

    def test_no_se_guarda_en_cache_http(self):
        self.assertIn('no-cache', self.client.get('/service-worker.js')['Cache-Control'])

    @override_settings(PWA_VERSION='42')
    def test_incluye_la_version_y_la_pagina_sin_conexion(self):
        js = self.client.get('/service-worker.js').content.decode()
        self.assertIn("const VERSION = '42'", js)
        self.assertIn("'/offline/'", js)
        self.assertNotIn('{{', js)          # ninguna variable de plantilla quedó sin resolver
        self.assertNotIn('{%', js)

    def test_las_rutas_precargadas_son_archivos_reales(self):
        js = self.client.get('/service-worker.js').content.decode()
        self.assertIn('/static/pwa/pwa.js', js)
        self.assertIsNotNone(finders.find('pwa/pwa.js'))

    def test_los_formularios_y_el_mapa_no_se_guardan(self):
        js = self.client.get('/service-worker.js').content.decode()
        self.assertNotIn('parcelas\\/nueva', js)
        self.assertNotIn('cuenta', js)


class RegistrosSinConexionTests(PruebaBase):
    """Piezas que permiten registrar sin señal y sincronizar después (CP-016)."""

    def setUp(self):
        from parcelas.tests import crear_distrito, crear_parcela
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, crear_distrito())
        self.client.force_login(self.usuario)

    def test_el_service_worker_guarda_las_pantallas_de_historial_y_suelo(self):
        js = self.client.get('/service-worker.js').content.decode()
        self.assertIn('historial|suelo', js)

    def test_el_service_worker_precarga_el_script_de_la_cola(self):
        js = self.client.get('/service-worker.js').content.decode()
        self.assertIn('/static/pwa/sincronizacion.js', js)
        self.assertIsNotNone(finders.find('pwa/sincronizacion.js'))

    def test_historial_y_suelo_usan_la_cola_del_celular(self):
        for nombre, tipo in (('historial', 'historial'), ('suelo', 'suelo')):
            r = self.client.get(reverse(f'parcelas:{nombre}', args=[self.parcela.pk]))
            self.assertContains(r, f'data-pwa-form="{tipo}"')
            self.assertContains(r, f'data-parcela="{self.parcela.pk}"')
            self.assertContains(r, f'data-tipo="{tipo}"')
            self.assertContains(r, f'data-usuario="{self.usuario.pk}"')       # la cola es por usuario

    def test_sin_sesion_la_pagina_no_declara_usuario(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse('usuarios:login')), 'data-usuario=""')

    def test_la_lista_de_parcelas_manda_guardar_historial_y_suelo(self):
        r = self.client.get(reverse('parcelas:lista'))
        self.assertContains(r, 'data-pwa-precargar', count=2)


class SinConexionTests(PruebaBase):
    def test_la_pagina_sin_conexion_abre_sin_sesion(self):
        r = self.client.get(reverse('pwa:offline'))
        self.assertContains(r, 'Sin conexión')
        self.assertContains(r, 'Mis recomendaciones')


class PlantillaBaseTests(PruebaBase):
    def test_las_paginas_enlazan_manifiesto_y_script(self):
        r = self.client.get(reverse('usuarios:login'))
        self.assertContains(r, 'rel="manifest"')
        self.assertContains(r, 'name="theme-color"')
        self.assertContains(r, 'apple-touch-icon')
        self.assertContains(r, 'pwa/pwa.js')
        self.assertContains(r, 'id="btn-instalar"')

    def test_cerrar_sesion_limpia_la_cache_del_celular(self):
        self.client.force_login(self.crear_usuario())
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'data-pwa-salir')