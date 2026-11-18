from django.urls import reverse

from parcelas.models import HistorialCampana
from parcelas.tests import crear_cultivo, crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase

from . import servicio
from .models import Recomendacion

from datetime import date
from parcelas.models import AnalisisSuelo, HistorialCampana


def distrito_tiabaya():
    return crear_distrito(ubigeo='040123', nombre='Tiabaya')


class ServicioTests(PruebaBase):
    def test_clave_por_ubigeo(self):
        self.assertEqual(servicio.clave_distrito(distrito_tiabaya()), 'TIABAYA')

    def test_distrito_fuera_del_modelo(self):
        with self.assertRaises(servicio.DistritoNoCubierto):
            servicio.clave_distrito(crear_distrito())          # Arequipa (040101)

    def test_ranking_ordenado_de_mayor_a_menor(self):
        parcela = crear_parcela(self.crear_usuario(), distrito_tiabaya())
        ranking = servicio.recomendar_para_parcela(parcela, 11)['ranking']
        valores = [r['idoneidad_ajustada'] for r in ranking]
        self.assertEqual(valores, sorted(valores, reverse=True))
        self.assertEqual(len(ranking), 10)

    def test_el_historial_cambia_la_recomendacion(self):
        parcela = crear_parcela(self.crear_usuario(), distrito_tiabaya())
        sin = servicio.recomendar_para_parcela(parcela, 11)
        self.assertIsNone(sin['antecesor'])
        arveja = crear_cultivo('Arveja Grano Verde', codigo='14030050000')
        HistorialCampana.objects.create(parcela=parcela, cultivo=arveja, campana_ini=2025, resultado='bueno')
        con = servicio.recomendar_para_parcela(parcela, 11)
        self.assertEqual(con['antecesor'], 'Arveja Grano Verde')
        self.assertNotEqual([r['idoneidad'] for r in sin['ranking']],
                            [r['idoneidad'] for r in con['ranking']])

    def test_antecesor_desconocido_no_rompe(self):
        parcela = crear_parcela(self.crear_usuario(), distrito_tiabaya())
        raro = crear_cultivo('Cultivo Inventado', codigo='999')
        HistorialCampana.objects.create(parcela=parcela, cultivo=raro, campana_ini=2025, resultado='bueno')
        datos = servicio.recomendar_para_parcela(parcela, 11)
        self.assertIsNone(datos['antecesor'])


class SueloTests(PruebaBase):
    """RF-0004: estimación por zona y análisis de laboratorio opcional."""

    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, distrito_tiabaya())

    def test_sin_analisis_usa_la_estimacion_de_la_zona(self):          # CP-007
        s = servicio.recomendar_para_parcela(self.parcela, 11)['suelo']
        self.assertFalse(s['ph']['medido'])
        self.assertFalse(s['arcilla']['medido'])
        self.assertIsNotNone(s['ph']['valor'])
        self.assertEqual(s['fecha'], '')

    def test_el_analisis_reemplaza_la_estimacion(self):                # CP-008
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=5.2, arcilla=30)
        s = servicio.recomendar_para_parcela(self.parcela, 11)['suelo']
        self.assertEqual((s['ph']['valor'], s['ph']['medido']), (5.2, True))
        self.assertEqual((s['arcilla']['valor'], s['arcilla']['medido']), (30.0, True))
        self.assertEqual(s['fecha'], '10/03/2026')

    def test_el_analisis_cambia_el_resultado(self):
        sin = servicio.recomendar_para_parcela(self.parcela, 11)['ranking']
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=5.2, arcilla=30)
        con = servicio.recomendar_para_parcela(self.parcela, 11)['ranking']
        self.assertNotEqual({r['cultivo']: r['idoneidad'] for r in sin},
                            {r['cultivo']: r['idoneidad'] for r in con})

    def test_analisis_parcial_se_completa_con_la_zona(self):
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=5.2)
        s = servicio.recomendar_para_parcela(self.parcela, 11)['suelo']
        self.assertTrue(s['ph']['medido'])
        self.assertFalse(s['arcilla']['medido'])
        self.assertIsNotNone(s['arcilla']['valor'])

    def test_usa_siempre_el_analisis_mas_reciente(self):
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2023, 3, 10), ph=5.0)
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=7.0)
        self.assertEqual(servicio.recomendar_para_parcela(self.parcela, 11)['suelo']['ph']['valor'], 7.0)

    def test_el_analisis_de_otra_parcela_no_se_mezcla(self):
        otra = crear_parcela(self.usuario, self.parcela.distrito, nombre='Otra')
        AnalisisSuelo.objects.create(parcela=otra, fecha=date(2026, 3, 10), ph=5.0)
        self.assertFalse(servicio.recomendar_para_parcela(self.parcela, 11)['suelo']['ph']['medido'])


class VistasTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, distrito_tiabaya())
        self.client.force_login(self.usuario)

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.get(reverse('recomendaciones:generar', args=[self.parcela.pk]))
        self.assertEqual(r.status_code, 302)

    def test_formulario_se_muestra(self):
        r = self.client.get(reverse('recomendaciones:generar', args=[self.parcela.pk]))
        self.assertContains(r, 'En qué mes piensa sembrar')

    def test_generar_guarda_y_muestra(self):
        r = self.client.post(reverse('recomendaciones:generar', args=[self.parcela.pk]), {'mes': '11'})
        rec = Recomendacion.objects.get()
        self.assertRedirects(r, reverse('recomendaciones:detalle', args=[rec.pk]))
        self.assertEqual(rec.mes, 11)
        self.assertEqual(len(rec.resultado), 10)
        r = self.client.get(reverse('recomendaciones:detalle', args=[rec.pk]))
        self.assertContains(r, rec.resultado[0]['cultivo'])

    def test_mes_invalido_usa_el_mes_actual(self):
        self.client.post(reverse('recomendaciones:generar', args=[self.parcela.pk]), {'mes': '99'})
        self.assertTrue(1 <= Recomendacion.objects.get().mes <= 12)

    def test_distrito_no_cubierto_avisa_y_no_guarda(self):
        otra = crear_parcela(self.usuario, crear_distrito(), nombre='Otra')
        url = reverse('recomendaciones:generar', args=[otra.pk])
        self.assertContains(self.client.get(url), 'disponibles para los distritos')
        self.client.post(url, {'mes': '11'})
        self.assertEqual(Recomendacion.objects.count(), 0)

    def test_no_se_ve_la_de_otro_usuario(self):
        self.client.post(reverse('recomendaciones:generar', args=[self.parcela.pk]), {'mes': '11'})
        rec = Recomendacion.objects.get()
        self.client.logout()
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse('recomendaciones:detalle', args=[rec.pk])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('recomendaciones:generar', args=[self.parcela.pk])).status_code, 404)
        
    def test_detalle_dibuja_el_grafico_de_influencia(self):
        self.client.post(reverse('recomendaciones:generar', args=[self.parcela.pk]), {'mes': '11'})
        rec = Recomendacion.objects.get()
        r = self.client.get(reverse('recomendaciones:detalle', args=[rec.pk]))
        self.assertContains(r, 'Qué pesó más')
        self.assertContains(r, 'progress-bar')

    def test_recomendacion_antigua_sin_influencia_no_rompe(self):
        rec = Recomendacion.objects.create(parcela=self.parcela, mes=11, antecesor='', resultado=[{
            'puesto': 1, 'cultivo': 'Maiz Chala', 'idoneidad': 60, 'certeza_pct': 70, 'idoneidad_ajustada': 50,
            'nivel': 'Media', 'explicacion': 'x', 'explicacion_detallada': 'y'}])
        r = self.client.get(reverse('recomendaciones:detalle', args=[rec.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'Qué pesó más')
        
    def test_detalle_indica_el_origen_del_suelo(self):
        url = reverse('recomendaciones:generar', args=[self.parcela.pk])
        self.client.post(url, {'mes': '11'})
        r = self.client.get(reverse('recomendaciones:detalle', args=[Recomendacion.objects.get().pk]))
        self.assertContains(r, 'estimado para su zona')
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=5.2, arcilla=30)
        self.client.post(url, {'mes': '11'})
        r = self.client.get(reverse('recomendaciones:detalle', args=[Recomendacion.objects.first().pk]))
        self.assertContains(r, 'de su análisis del 10/03/2026')

    def test_recomendacion_antigua_sin_datos_de_suelo_no_rompe(self):
        rec = Recomendacion.objects.create(parcela=self.parcela, mes=11, resultado=[])   # sin campo suelo
        self.assertEqual(self.client.get(reverse('recomendaciones:detalle', args=[rec.pk])).status_code, 200)

    def test_formulario_invita_a_agregar_analisis(self):
        r = self.client.get(reverse('recomendaciones:generar', args=[self.parcela.pk]))
        self.assertContains(r, 'agregarlo aquí')
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 3, 10), ph=5.2)
        r = self.client.get(reverse('recomendaciones:generar', args=[self.parcela.pk]))
        self.assertContains(r, 'Se usará su análisis de suelo del 10/03/2026')


class InfluenciaTests(PruebaBase):
    def setUp(self):
        self.parcela = crear_parcela(self.crear_usuario(), distrito_tiabaya())

    def test_cada_cultivo_trae_influencia_ordenada(self):
        for r in servicio.recomendar_para_parcela(self.parcela, 11)['ranking']:
            inf = r['influencia']
            self.assertEqual({f['factor'] for f in inf}, {'temperatura', 'ph', 'textura'})  # sin antecesor
            pcts = [f['pct'] for f in inf]
            self.assertEqual(pcts, sorted(pcts, reverse=True))
            self.assertTrue(sum(pcts) == 0 or 97 <= sum(pcts) <= 103)   # 0 = ningún factor cambia el resultado

    def test_con_antecesor_aparece_ese_factor(self):
        arveja = crear_cultivo('Arveja Grano Verde', codigo='14030050000')
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=arveja, campana_ini=2025, resultado='bueno')
        r = servicio.recomendar_para_parcela(self.parcela, 11)['ranking'][0]
        self.assertIn('antecesor', {f['factor'] for f in r['influencia']})

    def test_detecta_factor_que_perjudica(self):
        ranking = servicio.recomendar_para_parcela(self.parcela, 1)['ranking']   # enero: la papa sufre por el pH
        papa = next(r for r in ranking if r['cultivo'].lower().startswith('papa'))
        ph = next(f for f in papa['influencia'] if f['factor'] == 'ph')
        self.assertFalse(ph['ayuda'])
        
        
class ListaTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, distrito_tiabaya())
        self.client.force_login(self.usuario)
        self.url = reverse('recomendaciones:lista')

    def _crear(self, mes=11, parcela=None, cultivo='Maiz Chala'):
        return Recomendacion.objects.create(parcela=parcela or self.parcela, mes=mes, resultado=[{
            'puesto': 1, 'cultivo': cultivo, 'idoneidad': 60, 'certeza_pct': 70, 'idoneidad_ajustada': 50,
            'nivel': 'Media', 'explicacion': 'x', 'explicacion_detallada': 'y'}])

    def test_requiere_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_sin_recomendaciones_orienta_al_usuario(self):
        self.assertContains(self.client.get(self.url), 'Todavía no pidió ninguna recomendación')

    def test_muestra_parcela_mes_y_mejor_cultivo(self):
        self._crear(mes=11, cultivo='Arveja Grano Verde')
        r = self.client.get(self.url)
        self.assertContains(r, self.parcela.nombre)
        self.assertContains(r, 'noviembre')
        self.assertContains(r, 'Arveja Grano Verde')

    def test_solo_muestra_las_propias(self):
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        ajena = crear_parcela(otro, self.parcela.distrito, nombre='Ajena')
        self._crear(parcela=ajena, cultivo='Papa')
        self.assertNotContains(self.client.get(self.url), 'Ajena')

    def test_la_mas_reciente_va_primero(self):
        vieja = self._crear(mes=1)
        nueva = self._crear(mes=2)
        enlaces = self.client.get(self.url).content.decode()
        self.assertLess(enlaces.index(reverse('recomendaciones:detalle', args=[nueva.pk])),
                        enlaces.index(reverse('recomendaciones:detalle', args=[vieja.pk])))

    def test_limita_a_20_y_marca_10_para_guardar_sin_conexion(self):
        for _ in range(25):
            self._crear()
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('class="card shadow-sm mb-2 text-decoration-none'), 20)
        self.assertEqual(html.count('data-pwa-precargar'), 10)

    def test_una_recomendacion_antigua_sin_resultado_no_rompe(self):
        Recomendacion.objects.create(parcela=self.parcela, mes=3, resultado=[])
        self.assertEqual(self.client.get(self.url).status_code, 200)