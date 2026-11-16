from django.urls import reverse

from parcelas.models import HistorialCampana
from parcelas.tests import crear_cultivo, crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase

from . import servicio
from .models import Recomendacion


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