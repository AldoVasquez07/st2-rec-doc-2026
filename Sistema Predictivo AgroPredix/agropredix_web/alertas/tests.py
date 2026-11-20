from datetime import date, timedelta

from django.urls import reverse

from clima.models import RegistroClima
from parcelas.tests import crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase

from . import servicio

HOY = date(2026, 11, 19)


def cargar_clima(distrito, humedad, temp, lluvia=0.0, dias=7, fin=None):
    fin = fin or date.today()
    for i in range(dias):
        RegistroClima.objects.create(distrito=distrito, fecha=fin - timedelta(days=i), temp_media=temp,
                                     humedad=humedad, precipitacion=lluvia)


def alerta(alertas, id_):
    return next(a for a in alertas if a['id'] == id_)


class ReglasTests(PruebaBase):
    def setUp(self):
        self.d = crear_distrito()

    def test_humedad_y_temperatura_templada_dan_riesgo_alto_de_hongos(self):
        cargar_clima(self.d, humedad=85, temp=17)
        a = alerta(servicio.alertas_de_distrito(self.d), 'hongos_foliares')
        self.assertEqual(a['nivel'], 'alto')
        self.assertEqual(a['color'], 'danger')
        self.assertIn('85 %', a['factor'])                       # indica qué factor lo causó
        self.assertIn('17 °C', a['factor'])

    def test_nivel_medio(self):
        cargar_clima(self.d, humedad=74, temp=17)
        self.assertEqual(alerta(servicio.alertas_de_distrito(self.d), 'hongos_foliares')['nivel'], 'medio')

    def test_clima_seco_y_templado_no_da_riesgo_de_hongos(self):
        cargar_clima(self.d, humedad=40, temp=16)
        a = alerta(servicio.alertas_de_distrito(self.d), 'hongos_foliares')
        self.assertEqual(a['nivel'], 'bajo')
        self.assertEqual(a['color'], 'success')

    def test_calor_y_sequedad_dan_riesgo_de_plagas(self):
        cargar_clima(self.d, humedad=35, temp=26)
        a = alerta(servicio.alertas_de_distrito(self.d), 'plagas_calor_seco')
        self.assertEqual((a['nivel'], a['tipo']), ('alto', 'plaga'))

    def test_lluvia_baja_el_riesgo_de_plagas_de_alto_a_medio(self):
        cargar_clima(self.d, humedad=35, temp=26, lluvia=3)
        self.assertEqual(alerta(servicio.alertas_de_distrito(self.d), 'plagas_calor_seco')['nivel'], 'medio')

    def test_ordenadas_de_mayor_a_menor_riesgo(self):
        cargar_clima(self.d, humedad=85, temp=17)
        orden = [a['nivel'] for a in servicio.alertas_de_distrito(self.d)]
        self.assertEqual(orden, sorted(orden, key=servicio.ORDEN.get))

    def test_con_pocos_datos_no_opina(self):
        cargar_clima(self.d, humedad=85, temp=17, dias=2)
        self.assertIsNone(servicio.alertas_de_distrito(self.d))

    def test_sin_datos_no_opina(self):
        self.assertIsNone(servicio.alertas_de_distrito(self.d))

    def test_todas_las_reglas_tienen_los_dos_niveles_y_plantillas(self):
        for regla in servicio.cargar_reglas()['reglas']:
            self.assertEqual(set(regla['niveles']), {'medio', 'alto'})
            regla['factor'].format(humedad_media=1, temp_media=1, precip_total=1, dias=7)
            regla['sin_riesgo'].format(dias=7)


class PanelTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.d = crear_distrito()
        self.parcela = crear_parcela(self.usuario, self.d)
        self.client.force_login(self.usuario)

    def test_alerta_alta_aparece_en_el_panel_principal(self):
        cargar_clima(self.d, humedad=85, temp=17)
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'Riesgo alto')
        self.assertContains(r, 'alert-danger')
        self.assertContains(r, 'Mi chacra')

    def test_las_altas_van_antes_que_las_medias(self):
        cargar_clima(self.d, humedad=85, temp=21)         # hongos medio/alto según rango; plagas no
        otra = crear_distrito(ubigeo='040102', nombre='Otro')
        crear_parcela(self.usuario, otra, nombre='Zeta')
        cargar_clima(otra, humedad=35, temp=26)           # plagas alto
        niveles = [a['nivel'] for a in servicio.alertas_de_usuario(self.usuario)]
        self.assertEqual(niveles, sorted(niveles, key=servicio.ORDEN.get))

    def test_sin_riesgo_no_ensucia_el_panel(self):
        cargar_clima(self.d, humedad=40, temp=16)
        r = self.client.get(reverse('home'))
        self.assertNotContains(r, 'Riesgo alto')
        self.assertNotContains(r, 'Riesgo medio')

    def test_el_panel_funciona_sin_datos_de_clima(self):
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_no_muestra_alertas_de_parcelas_ajenas(self):
        otro = self.crear_usuario(nombre='Otro', celular='955555555')
        dist = crear_distrito(ubigeo='040103', nombre='Lejos')
        crear_parcela(otro, dist, nombre='Ajena')
        cargar_clima(dist, humedad=85, temp=17)
        self.assertEqual(servicio.alertas_de_usuario(self.usuario), [])
