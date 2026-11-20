from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.urls import reverse

from parcelas.tests import crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase

from . import fuentes, servicio
from .models import ActualizacionClima, RegistroClima

HOY = date(2026, 11, 19)


def dias_falsos(inicio, fin, **extra):
    dia, salida = inicio, []
    while dia <= fin:
        salida.append({'fecha': dia, 'temp_media': 17.0, 'temp_max': 24.0, 'temp_min': 10.0,
                       'humedad': 60.0, 'precipitacion': 0.0, **extra})
        dia += timedelta(days=1)
    return salida


def fuente_ok(lat, lon, inicio, fin):
    return dias_falsos(inicio, fin)


def fuente_caida(lat, lon, inicio, fin):
    raise fuentes.FuenteNoDisponible('sin conexión')


class FuenteTests(PruebaBase):
    def test_normaliza_respuesta_de_nasa_power(self):
        p = {'T2M': {'20261101': 17.5, '20261102': -999}, 'T2M_MAX': {'20261101': 24.0, '20261102': -999},
             'T2M_MIN': {'20261101': 10.1, '20261102': -999}, 'RH2M': {'20261101': 55.2, '20261102': -999},
             'PRECTOTCORR': {'20261101': 0.0, '20261102': -999}}
        dias = fuentes.normalizar(p)
        self.assertEqual(len(dias), 1)                       # el día sin ningún dato se descarta
        self.assertEqual(dias[0]['fecha'], date(2026, 11, 1))
        self.assertEqual(dias[0]['humedad'], 55.2)

    def test_error_de_red_se_convierte_en_fuente_no_disponible(self):
        with mock.patch('urllib.request.urlopen', side_effect=OSError('sin red')):
            with self.assertRaises(fuentes.FuenteNoDisponible):
                fuentes.descargar(-16.4, -71.5, HOY - timedelta(days=5), HOY)

    def test_respuesta_con_formato_inesperado(self):
        with mock.patch('urllib.request.urlopen') as u:
            u.return_value.__enter__.return_value.read.return_value = b'{"x": 1}'
            with self.assertRaises(fuentes.FuenteNoDisponible):
                fuentes.descargar(-16.4, -71.5, HOY - timedelta(days=5), HOY)


class ServicioTests(PruebaBase):
    def setUp(self):
        self.distrito = crear_distrito()

    def test_guarda_los_dias_descargados(self):
        n = servicio.actualizar_distrito(self.distrito, dias=10, descargar=fuente_ok, hoy=HOY)
        self.assertEqual(n, 11)
        self.assertEqual(RegistroClima.objects.count(), 11)
        self.assertTrue(ActualizacionClima.objects.get().exito)

    def test_actualizar_dos_veces_no_duplica(self):
        servicio.actualizar_distrito(self.distrito, dias=10, descargar=fuente_ok, hoy=HOY)
        servicio.actualizar_distrito(self.distrito, dias=10, descargar=fuente_ok, hoy=HOY + timedelta(days=1))
        self.assertEqual(RegistroClima.objects.filter(distrito=self.distrito).count(),
                         RegistroClima.objects.values('fecha').distinct().count())

    def test_fuente_caida_conserva_lo_guardado_y_lo_anota(self):
        servicio.actualizar_distrito(self.distrito, dias=10, descargar=fuente_ok, hoy=HOY)
        antes = RegistroClima.objects.count()
        self.assertIsNone(servicio.actualizar_distrito(self.distrito, descargar=fuente_caida, hoy=HOY))
        self.assertEqual(RegistroClima.objects.count(), antes)
        est = servicio.estado(self.distrito, hoy=HOY)
        self.assertTrue(est['fuente_fallo'])
        self.assertTrue(est['desactualizado'])
        self.assertEqual(est['ultimo_dato'], HOY - timedelta(days=servicio.RETRASO_FUENTE))

    def test_distrito_sin_coordenadas(self):
        d = crear_distrito(ubigeo='040199', nombre='Sin coordenadas', lat=None, lon=None)
        self.assertIsNone(servicio.actualizar_distrito(d, descargar=fuente_ok, hoy=HOY))
        self.assertFalse(ActualizacionClima.objects.get(distrito=d).exito)

    def test_datos_viejos_se_marcan_desactualizados(self):
        servicio.actualizar_distrito(self.distrito, dias=10, descargar=fuente_ok, hoy=HOY)
        self.assertFalse(servicio.estado(self.distrito, hoy=HOY)['desactualizado'])
        self.assertTrue(servicio.estado(self.distrito, hoy=HOY + timedelta(days=20))['desactualizado'])

    def test_serie_se_cuenta_desde_el_ultimo_dato(self):
        servicio.actualizar_distrito(self.distrito, dias=60, descargar=fuente_ok, hoy=HOY)
        self.assertEqual(len(servicio.serie(self.distrito, 30)), 30)

    def test_comando_actualiza_solo_distritos_con_parcelas(self):
        otro = crear_distrito(ubigeo='040102', nombre='Otro')
        crear_parcela(self.crear_usuario(), self.distrito)
        with mock.patch('clima.fuentes.descargar', side_effect=fuente_ok):
            call_command('actualizar_clima', stdout=StringIO())
        self.assertTrue(RegistroClima.objects.filter(distrito=self.distrito).exists())
        self.assertFalse(RegistroClima.objects.filter(distrito=otro).exists())

    def test_comando_no_falla_si_la_fuente_cae(self):
        crear_parcela(self.crear_usuario(), self.distrito)
        with mock.patch('clima.fuentes.descargar', side_effect=fuente_caida):
            call_command('actualizar_clima', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(RegistroClima.objects.count(), 0)


class VistaTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.distrito = crear_distrito()
        self.parcela = crear_parcela(self.usuario, self.distrito)
        self.url = reverse('clima:parcela', args=[self.parcela.pk])

    def test_exige_sesion(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_no_se_ve_la_parcela_de_otro(self):
        otro = self.crear_usuario(nombre='Otro', celular='955555555')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_sin_datos_avisa(self):
        self.client.force_login(self.usuario)
        r = self.client.get(self.url)
        self.assertContains(r, 'Todavía no tenemos datos')

    def test_con_datos_muestra_graficos(self):
        servicio.actualizar_distrito(self.distrito, dias=40, descargar=fuente_ok, hoy=date.today())
        self.client.force_login(self.usuario)
        r = self.client.get(self.url)
        self.assertContains(r, 'g-temp')
        self.assertContains(r, 'datos-clima')
        self.assertNotContains(r, 'No pudimos actualizar')

    def test_fuente_caida_muestra_ultimo_dato_con_su_fecha(self):
        servicio.actualizar_distrito(self.distrito, dias=40, descargar=fuente_ok, hoy=date.today())
        servicio.actualizar_distrito(self.distrito, descargar=fuente_caida, hoy=date.today())
        self.client.force_login(self.usuario)
        r = self.client.get(self.url)
        self.assertContains(r, 'No pudimos actualizar el clima')
        ultimo = date.today() - timedelta(days=servicio.RETRASO_FUENTE)
        self.assertContains(r, f'{ultimo:%d/%m/%Y}')
        self.assertContains(r, 'g-temp')                       # los gráficos siguen con lo guardado

    def test_rango_invalido_usa_el_de_30_dias(self):
        servicio.actualizar_distrito(self.distrito, dias=60, descargar=fuente_ok, hoy=date.today())
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url + '?dias=abc').status_code, 200)
        self.assertEqual(self.client.get(self.url + '?dias=9999').context['dias'], 30)
