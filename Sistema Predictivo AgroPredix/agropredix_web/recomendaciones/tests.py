from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from cultivos.models import Cultivo
from parcelas.models import AnalisisSuelo, HistorialCampana
from parcelas.tests import crear_cultivo, crear_distrito, crear_parcela
from usuarios.base_pruebas import PruebaBase

from . import seguimiento, servicio
from .models import Recomendacion, Siembra




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
        
        
# ---------- RETROALIMENTACIÓN POST-CAMPAÑA (RF-0011) ----------
class SeguimientoBase(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, distrito_tiabaya())
        self.client.force_login(self.usuario)
        self.client.post(reverse('recomendaciones:generar', args=[self.parcela.pk]), {'mes': '11'})
        self.rec = Recomendacion.objects.get()
        self.top = self.rec.resultado[0]
        self.cod = self.top['cod']
        self.url_sembrar = reverse('recomendaciones:sembrar', args=[self.rec.pk, self.cod])
        self.hoy = date.today()

    def sembrar(self, **datos):
        base = {'fecha_siembra': self.hoy.isoformat(), 'cierre_estimado': ''}
        base.update(datos)
        return self.client.post(self.url_sembrar, base)

    def siembra(self, dias=0, **extra):
        """Una siembra ya creada cuyo cierre estimado es hoy + dias."""
        return Siembra.objects.create(
            recomendacion=self.rec, cultivo_cod=self.cod, cultivo=self.top['cultivo'], puesto=1, idoneidad=60,
            certeza_pct=70, fecha_siembra=self.hoy - timedelta(days=100),
            cierre_estimado=self.hoy + timedelta(days=dias), **extra)


class SembrarTests(SeguimientoBase):
    def test_la_recomendacion_guarda_el_codigo_de_cada_cultivo(self):
        self.assertTrue(all(r.get('cod') for r in self.rec.resultado))

    def test_el_detalle_ofrece_sembrar_cada_cultivo(self):
        r = self.client.get(reverse('recomendaciones:detalle', args=[self.rec.pk]))
        self.assertContains(r, 'Voy a sembrar este', count=len(self.rec.resultado))

    def test_recomendacion_antigua_sin_codigo_no_ofrece_sembrar(self):
        vieja = Recomendacion.objects.create(parcela=self.parcela, mes=3, resultado=[{
            'puesto': 1, 'cultivo': 'Papa', 'idoneidad': 60, 'certeza_pct': 70, 'idoneidad_ajustada': 50,
            'nivel': 'Media', 'explicacion': 'x', 'explicacion_detallada': 'y'}])
        self.assertNotContains(self.client.get(reverse('recomendaciones:detalle', args=[vieja.pk])), 'Voy a sembrar')

    def test_el_formulario_propone_el_mes_consultado(self):
        r = self.client.get(self.url_sembrar)
        self.assertContains(r, 'Voy a sembrar')
        self.assertEqual(r.context['form'].initial['fecha_siembra'].month, 11)

    def test_registra_la_siembra_con_lo_que_el_motor_habia_calculado(self):
        self.assertEqual(self.sembrar().status_code, 302)
        s = Siembra.objects.get()
        self.assertEqual((s.recomendacion, s.cultivo_cod, s.cultivo), (self.rec, self.cod, self.top['cultivo']))
        self.assertEqual((s.puesto, s.idoneidad, s.certeza_pct),
                         (self.top['puesto'], self.top['idoneidad'], self.top['certeza_pct']))
        self.assertEqual(s.parcela, self.parcela)
        self.assertFalse(s.valorada)

    def test_el_cierre_se_calcula_con_el_ciclo_del_cultivo(self):
        crear_cultivo('Cultivo A', codigo=self.cod)
        Cultivo.objects.filter(codigo=self.cod).update(ciclo_dias=100)
        self.sembrar()
        s = Siembra.objects.get()
        self.assertEqual(s.cierre_estimado, s.fecha_siembra + timedelta(days=100))

    def test_sin_ciclo_cargado_usa_el_valor_por_defecto(self):
        self.sembrar()
        s = Siembra.objects.get()
        self.assertEqual(s.cierre_estimado, s.fecha_siembra + timedelta(days=seguimiento.CICLO_POR_DEFECTO))

    def test_respeta_la_fecha_de_cosecha_que_indique_el_agricultor(self):
        self.sembrar(cierre_estimado=(self.hoy + timedelta(days=75)).isoformat())
        self.assertEqual(Siembra.objects.get().cierre_estimado, self.hoy + timedelta(days=75))

    def test_rechaza_cosecha_antes_de_la_siembra(self):
        r = self.sembrar(cierre_estimado=(self.hoy - timedelta(days=1)).isoformat())
        self.assertContains(r, 'después de la siembra')
        self.assertEqual(Siembra.objects.count(), 0)

    def test_rechaza_fechas_fuera_de_rango(self):
        self.sembrar(fecha_siembra=(self.hoy + timedelta(days=800)).isoformat())
        self.sembrar(fecha_siembra=(self.hoy - timedelta(days=800)).isoformat())
        self.assertEqual(Siembra.objects.count(), 0)

    def test_no_se_duplica_la_siembra_del_mismo_cultivo(self):
        self.sembrar()
        self.sembrar()
        self.assertEqual(Siembra.objects.count(), 1)

    def test_cultivo_que_no_esta_en_la_recomendacion_da_404(self):
        url = reverse('recomendaciones:sembrar', args=[self.rec.pk, '999'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_requiere_sesion_y_es_solo_del_dueno(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url_sembrar).status_code, 302)
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url_sembrar).status_code, 404)
        self.assertEqual(self.sembrar().status_code, 404)
        self.assertEqual(Siembra.objects.count(), 0)

    def test_el_detalle_marca_lo_ya_sembrado(self):
        self.sembrar()
        r = self.client.get(reverse('recomendaciones:detalle', args=[self.rec.pk]))
        self.assertContains(r, 'Lo sembró el')
        self.assertContains(r, 'Voy a sembrar este', count=len(self.rec.resultado) - 1)


class PendientesTests(SeguimientoBase):
    def test_solo_pide_valorar_cuando_llega_el_cierre_estimado(self):
        s = self.siembra(dias=30)
        self.assertEqual(list(seguimiento.pendientes_de_valorar(self.usuario)), [])
        Siembra.objects.filter(pk=s.pk).update(cierre_estimado=self.hoy)
        self.assertEqual(list(seguimiento.pendientes_de_valorar(self.usuario)), [Siembra.objects.get()])

    def test_las_ya_valoradas_no_se_vuelven_a_pedir(self):
        self.siembra(dias=-5, resultado='bueno')
        self.assertEqual(list(seguimiento.pendientes_de_valorar(self.usuario)), [])

    def test_no_mezcla_con_las_de_otro_usuario(self):
        self.siembra(dias=-5)
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        self.assertEqual(list(seguimiento.pendientes_de_valorar(otro)), [])

    def test_la_portada_pregunta_cuando_hay_una_pendiente(self):
        self.siembra(dias=-5)
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'Contar cómo me fue')
        self.assertContains(r, self.top['cultivo'])

    def test_la_portada_no_molesta_si_no_hay_pendientes(self):
        self.siembra(dias=40)
        self.assertNotContains(self.client.get(reverse('home')), 'Contar cómo me fue')

    def test_la_pantalla_de_siembras_separa_pendientes_en_curso_y_valoradas(self):
        a = self.siembra(dias=-5)
        r = self.client.get(reverse('recomendaciones:seguimiento'))
        self.assertEqual([s.pk for s in r.context['pendientes']], [a.pk])
        self.assertEqual((r.context['en_curso'], r.context['valoradas']), ([], []))
        Siembra.objects.filter(pk=a.pk).update(cierre_estimado=self.hoy + timedelta(days=9))
        r = self.client.get(reverse('recomendaciones:seguimiento'))
        self.assertEqual(len(r.context['en_curso']), 1)
        self.assertEqual(r.context['pendientes'], [])

    def test_sin_siembras_orienta_al_agricultor(self):
        self.assertContains(self.client.get(reverse('recomendaciones:seguimiento')), 'Todavía no registró ninguna siembra')


class ValorarTests(SeguimientoBase):
    def setUp(self):
        super().setUp()
        self.s = self.siembra(dias=-3)
        self.url = reverse('recomendaciones:valorar', args=[self.s.pk])

    def test_guarda_resultado_y_comentario_asociados_a_la_recomendacion_y_la_parcela(self):
        r = self.client.post(self.url, {'resultado': 'regular', 'comentario': 'Llegó tarde el agua'})
        self.assertRedirects(r, reverse('recomendaciones:seguimiento'))
        self.s.refresh_from_db()
        self.assertEqual((self.s.resultado, self.s.comentario), ('regular', 'Llegó tarde el agua'))
        self.assertIsNotNone(self.s.fecha_valoracion)
        self.assertEqual((self.s.recomendacion, self.s.parcela), (self.rec, self.parcela))

    def test_el_comentario_es_opcional(self):
        self.client.post(self.url, {'resultado': 'bueno'})
        self.s.refresh_from_db()
        self.assertEqual((self.s.resultado, self.s.comentario), ('bueno', ''))

    def test_el_resultado_es_obligatorio_y_solo_acepta_bueno_regular_malo(self):
        for datos in ({}, {'resultado': ''}, {'resultado': 'excelente'}):
            self.client.post(self.url, datos)
        self.s.refresh_from_db()
        self.assertFalse(self.s.valorada)

    def test_rechaza_comentarios_demasiado_largos(self):
        self.client.post(self.url, {'resultado': 'malo', 'comentario': 'x' * 301})
        self.s.refresh_from_db()
        self.assertFalse(self.s.valorada)

    def test_una_siembra_ya_valorada_no_se_cambia(self):
        self.client.post(self.url, {'resultado': 'bueno'})
        self.client.post(self.url, {'resultado': 'malo', 'comentario': 'cambié de idea'})
        self.s.refresh_from_db()
        self.assertEqual((self.s.resultado, self.s.comentario), ('bueno', ''))

    def test_se_puede_valorar_antes_de_la_fecha_estimada(self):
        Siembra.objects.filter(pk=self.s.pk).update(cierre_estimado=self.hoy + timedelta(days=30))
        self.client.post(self.url, {'resultado': 'bueno'})
        self.assertTrue(Siembra.objects.get(pk=self.s.pk).valorada)

    def test_requiere_sesion_y_es_solo_del_dueno(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'resultado': 'bueno'}).status_code, 404)
        self.assertFalse(Siembra.objects.get(pk=self.s.pk).valorada)


class HistorialDesdeValoracionTests(SeguimientoBase):
    def setUp(self):
        super().setUp()
        self.cultivo = crear_cultivo(self.top['cultivo'], codigo=self.cod)

    def valorar(self, s, resultado='bueno'):
        return self.client.post(reverse('recomendaciones:valorar', args=[s.pk]), {'resultado': resultado})

    def test_la_valoracion_queda_en_el_historial_de_la_parcela(self):
        s = self.siembra(dias=-3)
        r = self.valorar(s, 'bueno')
        h = HistorialCampana.objects.get()
        self.assertEqual((h.parcela, h.cultivo, h.resultado), (self.parcela, self.cultivo, 'bueno'))
        self.assertEqual(h.campana_ini, seguimiento.campana_de(s.fecha_siembra))
        self.assertContains(self.client.get(r['Location']), 'historial de su parcela')

    def test_si_ya_habia_un_registro_de_esa_campana_se_actualiza_sin_duplicar(self):
        s = self.siembra(dias=-3)
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.cultivo,
                                        campana_ini=seguimiento.campana_de(s.fecha_siembra), resultado='malo')
        self.valorar(s, 'regular')
        self.assertEqual(HistorialCampana.objects.count(), 1)
        self.assertEqual(HistorialCampana.objects.get().resultado, 'regular')

    def test_el_cultivo_valorado_pasa_a_ser_el_antecesor_de_la_proxima_recomendacion(self):
        self.assertIsNone(servicio.antecesor_de(self.parcela))
        self.valorar(self.siembra(dias=-3), 'bueno')
        self.assertEqual(servicio.antecesor_de(self.parcela), self.cultivo.nombre)

    def test_si_el_cultivo_no_esta_en_el_catalogo_igual_se_guarda_la_valoracion(self):
        self.cultivo.delete()
        s = self.siembra(dias=-3)
        self.valorar(s, 'malo')
        self.assertEqual(HistorialCampana.objects.count(), 0)
        self.assertEqual(Siembra.objects.get(pk=s.pk).resultado, 'malo')

    def test_la_campana_agricola_empieza_en_agosto(self):
        self.assertEqual(seguimiento.campana_de(date(2026, 9, 10)), 2026)
        self.assertEqual(seguimiento.campana_de(date(2026, 8, 1)), 2026)
        self.assertEqual(seguimiento.campana_de(date(2026, 7, 31)), 2025)
        self.assertEqual(seguimiento.campana_de(date(2026, 3, 10)), 2025)


class CiclosTests(PruebaBase):
    def test_carga_los_ciclos_sin_pisar_lo_que_ya_corrigio_el_agronomo(self):
        papa = crear_cultivo('Papa', codigo='14040090000')
        ajo = crear_cultivo('Ajo', codigo='14030030000')
        Cultivo.objects.filter(pk=ajo.pk).update(ciclo_dias=999)           # valor corregido a mano
        call_command('cargar_ciclos', stdout=StringIO())
        papa.refresh_from_db(); ajo.refresh_from_db()
        self.assertEqual((papa.ciclo_dias, ajo.ciclo_dias), (140, 999))

    def test_forzar_reemplaza_todo(self):
        ajo = crear_cultivo('Ajo', codigo='14030030000')
        Cultivo.objects.filter(pk=ajo.pk).update(ciclo_dias=999)
        call_command('cargar_ciclos', '--forzar', stdout=StringIO())
        ajo.refresh_from_db()
        self.assertEqual(ajo.ciclo_dias, 170)

    def test_los_diez_cultivos_del_modelo_tienen_ciclo_referencial(self):
        from cultivos.management.commands.cargar_ciclos import CICLOS_REFERENCIALES
        from .motor.agropredix_motor import cargar_modelo
        from .servicio import RUTA_MODELO
        self.assertEqual(set(cargar_modelo(RUTA_MODELO)['cultivos']), set(CICLOS_REFERENCIALES))