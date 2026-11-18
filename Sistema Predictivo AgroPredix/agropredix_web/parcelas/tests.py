import csv
import os
import tempfile
from datetime import date
from io import StringIO
from unittest import mock, skipUnless

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import Count, ProtectedError
from django.test import Client, SimpleTestCase, override_settings

from django.urls import reverse

from cultivos.models import Cultivo
from usuarios.base_pruebas import PruebaBase

from .forms import _campanas_anteriores
from .models import AnalisisSuelo, Distrito, HistorialCampana, Parcela

import json
import uuid

# ---------- ayudas ----------
def crear_distrito(ubigeo='040101', nombre='Arequipa', lat=-16.4, lon=-71.53):
    return Distrito.objects.create(ubigeo=ubigeo, nombre=nombre, provincia='Arequipa',
                                   latitud=lat, longitud=lon)


def crear_cultivo(nombre='Papa', codigo='1001', activo=True):
    return Cultivo.objects.create(codigo=codigo, nombre=nombre, grupo='raiz_tuberculo',
                                  tipo='transitorio', familia='Solanaceae', activo=activo)


def crear_parcela(usuario, distrito, nombre='Mi chacra'):
    return Parcela.objects.create(usuario=usuario, distrito=distrito, nombre=nombre,
                                  area_ha=1.5, latitud=-16.4, longitud=-71.53)


def escribir_csv(carpeta, nombre, columnas, filas):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
        escritor = csv.writer(f)
        escritor.writerow(columnas)
        escritor.writerows(filas)
    return ruta


RUTA_DISTRITOS = settings.BASE_DIR / 'datos' / 'coordenadas_distritos.csv'   # ajusta si tu CSV se llama distinto


# ---------- CARGA DE DATOS ----------
class CargaDistritosTests(PruebaBase):
    def csv_prueba(self, carpeta):
        return escribir_csv(
            carpeta, 'distritos.csv',
            ['cod_ubigeo', 'distrito', 'provincia', 'latitud', 'longitud'],
            [[40101, 'AREQUIPA', 'AREQUIPA', -16.39, -71.53],
             [40102, 'ALTO SELVA ALEGRE', 'AREQUIPA', '', '']])

    def test_carga_desde_csv(self):
        with tempfile.TemporaryDirectory() as carpeta:
            call_command('cargar_distritos', self.csv_prueba(carpeta), stdout=StringIO())
        a = Distrito.objects.get(ubigeo='040101')
        self.assertEqual((a.nombre, a.provincia), ('Arequipa', 'Arequipa'))
        self.assertAlmostEqual(a.latitud, -16.39)
        b = Distrito.objects.get(ubigeo='040102')
        self.assertEqual(b.nombre, 'Alto Selva Alegre')
        self.assertIsNone(b.latitud)

    def test_cargar_dos_veces_no_duplica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = self.csv_prueba(carpeta)
            call_command('cargar_distritos', ruta, stdout=StringIO())
            call_command('cargar_distritos', ruta, stdout=StringIO())
        self.assertEqual(Distrito.objects.count(), 2)

    @skipUnless(RUTA_DISTRITOS.exists(), 'falta datos/coordenadas_distritos.csv')
    def test_archivo_real_trae_los_109_distritos_de_arequipa(self):
        call_command('cargar_distritos', str(RUTA_DISTRITOS), stdout=StringIO())
        self.assertEqual(Distrito.objects.count(), 109)
        por_provincia = dict(Distrito.objects.values_list('provincia').annotate(n=Count('id')))
        self.assertEqual(por_provincia, {'Arequipa': 29, 'Camana': 8, 'Caraveli': 13, 'Castilla': 14,
                                         'Caylloma': 20, 'Condesuyos': 8, 'Islay': 6, 'La Union': 11})
        self.assertEqual(Distrito.objects.filter(latitud__isnull=True).count(), 0)      # todos centran el mapa
        for ubigeo in ('040123', '040117', '040124'):                                   # Tiabaya, Sachaca, Uchumayo
            self.assertTrue(Distrito.objects.filter(ubigeo=ubigeo).exists(), ubigeo)


# ---------- SEGURIDAD: aislamiento entre agricultores ----------
class AislamientoEntreUsuariosTests(PruebaBase):
    def setUp(self):
        self.distrito = crear_distrito()
        self.ana = self.crear_usuario('Ana', celular='911111111')
        self.beto = self.crear_usuario('Beto', celular='922222222')
        self.p_ana = crear_parcela(self.ana, self.distrito, 'Chacra de Ana')
        self.p_beto = crear_parcela(self.beto, self.distrito, 'Chacra de Beto')
        self.papa = crear_cultivo()
        self.h_beto = HistorialCampana.objects.create(
            parcela=self.p_beto, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        self.client.force_login(self.ana)

    def test_lista_solo_muestra_las_propias(self):
        r = self.client.get(reverse('parcelas:lista'))
        self.assertEqual(list(r.context['parcelas']), [self.p_ana])

    def test_editar_parcela_ajena_da_404(self):
        url = reverse('parcelas:editar', args=[self.p_beto.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        r = self.client.post(url, {'nombre': 'Robada', 'distrito': self.distrito.pk, 'area_ha': '2',
                                   'latitud': '-16.4', 'longitud': '-71.5', 'referencia': ''})
        self.assertEqual(r.status_code, 404)
        self.p_beto.refresh_from_db()
        self.assertEqual(self.p_beto.nombre, 'Chacra de Beto')

    def test_eliminar_parcela_ajena_da_404(self):
        r = self.client.post(reverse('parcelas:eliminar', args=[self.p_beto.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Parcela.objects.filter(pk=self.p_beto.pk).exists())

    def test_historial_de_parcela_ajena_da_404(self):
        url = reverse('parcelas:historial', args=[self.p_beto.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        r = self.client.post(url, {'campana_ini': _campanas_anteriores()[0][0],
                                   'cultivo': self.papa.pk, 'resultado': 'malo'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(HistorialCampana.objects.count(), 1)      # solo el de Beto

    def test_quitar_registro_de_historial_ajeno_da_404(self):
        url = reverse('parcelas:historial_eliminar', args=[self.p_beto.pk, self.h_beto.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(HistorialCampana.objects.filter(pk=self.h_beto.pk).exists())

    def test_quitar_registro_solo_acepta_post(self):
        h = HistorialCampana.objects.create(
            parcela=self.p_ana, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        url = reverse('parcelas:historial_eliminar', args=[self.p_ana.pk, h.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(HistorialCampana.objects.filter(pk=h.pk).exists())

    def test_registro_no_se_borra_con_la_parcela_equivocada(self):
        otra = crear_parcela(self.ana, self.distrito, 'Otra de Ana')
        h = HistorialCampana.objects.create(
            parcela=self.p_ana, cultivo=self.papa, campana_ini=2023, resultado='regular')
        url = reverse('parcelas:historial_eliminar', args=[otra.pk, h.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(HistorialCampana.objects.filter(pk=h.pk).exists())


# ---------- FUNCIONALES: RF-0002 parcelas ----------
class ParcelaFuncionalTests(PruebaBase):
    def setUp(self):
        self.distrito = crear_distrito()
        self.usuario = self.crear_usuario()
        self.client.force_login(self.usuario)

    def datos(self, **extra):
        base = {'nombre': 'Mi chacra', 'distrito': self.distrito.pk, 'area_ha': '1.5',
                'latitud': '-16.4', 'longitud': '-71.53', 'referencia': ''}
        base.update(extra)
        return base

    def test_crear_asigna_la_parcela_al_usuario_que_ingreso(self):
        otro = self.crear_usuario('Otro', celular='955555555')
        r = self.client.post(reverse('parcelas:crear'), self.datos(usuario=otro.pk))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Parcela.objects.get().usuario, self.usuario)

    def test_el_mapa_recibe_el_centro_de_cada_distrito(self):
        r = self.client.get(reverse('parcelas:crear'))
        self.assertEqual(r.context['centros'][self.distrito.pk], [-16.4, -71.53])

    def test_editar_y_eliminar_la_propia(self):
        p = crear_parcela(self.usuario, self.distrito, 'Vieja')
        r = self.client.post(reverse('parcelas:editar', args=[p.pk]), self.datos(nombre='Nueva'))
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.nombre, 'Nueva')
        r = self.client.post(reverse('parcelas:eliminar', args=[p.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Parcela.objects.filter(pk=p.pk).exists())

    def test_nombre_repetido_del_mismo_usuario_se_rechaza(self):
        crear_parcela(self.usuario, self.distrito, 'Mi chacra')
        r = self.client.post(reverse('parcelas:crear'), self.datos(nombre='MI CHACRA'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('nombre', r.context['form'].errors)
        self.assertEqual(Parcela.objects.count(), 1)

    def test_mismo_nombre_en_otro_usuario_si_se_permite(self):
        otro = self.crear_usuario('Otro', celular='955555555')
        crear_parcela(otro, self.distrito, 'Mi chacra')
        r = self.client.post(reverse('parcelas:crear'), self.datos())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Parcela.objects.count(), 2)

    def test_coordenadas_fuera_de_arequipa_se_rechazan(self):
        for campo, valor in [('latitud', '0'), ('latitud', '-20'), ('longitud', '-80'), ('longitud', '-60')]:
            r = self.client.post(reverse('parcelas:crear'), self.datos(**{campo: valor}))
            self.assertEqual(r.status_code, 200, f'{campo}={valor}')
            self.assertIn(campo, r.context['form'].errors, f'{campo}={valor}')
        self.assertEqual(Parcela.objects.count(), 0)

    def test_area_fuera_de_rango_se_rechaza(self):
        for valor in ['0', '-3', '20000']:
            r = self.client.post(reverse('parcelas:crear'), self.datos(area_ha=valor))
            self.assertIn('area_ha', r.context['form'].errors, valor)
        self.assertEqual(Parcela.objects.count(), 0)

    def test_la_ubicacion_en_el_mapa_es_obligatoria(self):
        datos = self.datos()
        del datos['latitud'], datos['longitud']
        r = self.client.post(reverse('parcelas:crear'), datos)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Marque la ubicación de su parcela en el mapa.', r.context['form'].errors['latitud'])
        self.assertEqual(Parcela.objects.count(), 0)


# ---------- FUNCIONALES: RF-0003 historial ----------
class HistorialTests(PruebaBase):
    def setUp(self):
        self.distrito = crear_distrito()
        self.usuario = self.crear_usuario()
        self.client.force_login(self.usuario)
        self.parcela = crear_parcela(self.usuario, self.distrito)
        self.papa = crear_cultivo('Papa', '1001')
        self.maiz = crear_cultivo('Maíz', '1002')
        self.campana = _campanas_anteriores()[0][0]
        self.url = reverse('parcelas:historial', args=[self.parcela.pk])

    def datos(self, **extra):
        base = {'campana_ini': self.campana, 'cultivo': self.papa.pk, 'resultado': 'bueno'}
        base.update(extra)
        return base

    def test_agregar_campana_al_historial(self):
        r = self.client.post(self.url, self.datos())
        self.assertEqual(r.status_code, 302)
        h = HistorialCampana.objects.get()
        self.assertEqual((h.parcela, h.cultivo, h.campana_ini, h.resultado),
                         (self.parcela, self.papa, self.campana, 'bueno'))

    def test_historial_en_orden_cronologico_descendente(self):
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.maiz, campana_ini=2022, resultado='malo')
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2023, resultado='regular')
        r = self.client.get(self.url)
        self.assertEqual([h.campana_ini for h in r.context['registros']], [2024, 2023, 2022])

    def test_resultado_solo_bueno_regular_o_malo(self):
        r = self.client.post(self.url, self.datos(resultado='excelente'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('resultado', r.context['form'].errors)
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_mismo_cultivo_en_la_misma_campana_se_rechaza(self):
        self.client.post(self.url, self.datos())
        r = self.client.post(self.url, self.datos(resultado='malo'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form'].non_field_errors())
        self.assertEqual(HistorialCampana.objects.count(), 1)

    def test_campana_fuera_de_la_lista_se_rechaza(self):
        r = self.client.post(self.url, self.datos(campana_ini=1900))
        self.assertIn('campana_ini', r.context['form'].errors)
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_cultivo_inactivo_no_se_puede_elegir(self):
        self.maiz.activo = False
        self.maiz.save()
        r = self.client.post(self.url, self.datos(cultivo=self.maiz.pk))
        self.assertIn('cultivo', r.context['form'].errors)
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_el_formulario_ofrece_solo_cultivos_activos(self):
        crear_cultivo('Antiguo', '1003', activo=False)
        r = self.client.get(self.url)
        self.assertEqual(set(r.context['form'].fields['cultivo'].queryset), {self.papa, self.maiz})

    def test_la_base_de_datos_impide_duplicados(self):
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        with self.assertRaises(IntegrityError), transaction.atomic():
            HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2024, resultado='malo')

    def test_no_se_puede_borrar_un_cultivo_usado_en_un_historial(self):
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        with self.assertRaises(ProtectedError):
            self.papa.delete()

    def test_al_borrar_la_parcela_se_borra_su_historial(self):
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2024, resultado='bueno')
        self.parcela.delete()
        self.assertEqual(HistorialCampana.objects.count(), 0)


class CampanasAnterioresTests(SimpleTestCase):
    def opciones(self, hoy):
        with mock.patch('parcelas.forms.date') as falso:
            falso.today.return_value = hoy
            return _campanas_anteriores()

    def test_despues_de_agosto_la_ultima_campana_es_la_que_acaba_de_terminar(self):
        o = self.opciones(date(2026, 11, 13))
        self.assertEqual(o[0], (2025, '2025-2026'))
        self.assertEqual(len(o), 10)
        self.assertEqual(o[-1][0], 2016)

    def test_antes_de_agosto_la_campana_vigente_aun_no_termina(self):
        o = self.opciones(date(2026, 3, 1))
        self.assertEqual(o[0], (2024, '2024-2025'))
        

# ---------- GOOGLE MAPS ----------
class MapaGoogleTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.client.force_login(self.usuario)

    @override_settings(GOOGLE_MAPS_API_KEY='CLAVE_DE_PRUEBA', GOOGLE_MAPS_MAP_ID='MI_MAP_ID')
    def test_formulario_entrega_clave_y_map_id(self):
        r = self.client.get(reverse('parcelas:crear'))
        self.assertEqual(r.context['google_maps'], {'key': 'CLAVE_DE_PRUEBA', 'mapId': 'MI_MAP_ID'})
        self.assertContains(r, 'maps-config')
        self.assertContains(r, 'importLibrary')

    def test_ya_no_usa_leaflet(self):
        r = self.client.get(reverse('parcelas:crear'))
        self.assertNotContains(r, 'leaflet')
        self.assertNotContains(r, 'openstreetmap')

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_sin_clave_el_formulario_sigue_cargando(self):
        r = self.client.get(reverse('parcelas:crear'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['google_maps']['key'], '')
        

# ---------- ANÁLISIS DE SUELO (RF-0004) ----------
class AnalisisSueloTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, crear_distrito())
        self.url = reverse('parcelas:suelo', args=[self.parcela.pk])
        self.client.force_login(self.usuario)

    def _enviar(self, **datos):
        base = {'fecha': date.today().isoformat(), 'ph': '7.2', 'arcilla': '25', 'laboratorio': ''}
        base.update(datos)
        return self.client.post(self.url, base)

    def test_requiere_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_guarda_analisis_completo(self):
        self.assertRedirects(self._enviar(), self.url)
        a = AnalisisSuelo.objects.get()
        self.assertEqual((a.parcela, a.ph, a.arcilla), (self.parcela, 7.2, 25.0))

    def test_alcanza_con_el_ph_solo(self):
        self._enviar(arcilla='')
        self.assertIsNone(AnalisisSuelo.objects.get().arcilla)

    def test_rechaza_si_no_trae_ningun_valor(self):
        r = self._enviar(ph='', arcilla='')
        self.assertContains(r, 'al menos el pH')
        self.assertEqual(AnalisisSuelo.objects.count(), 0)

    def test_rechaza_valores_imposibles(self):
        self._enviar(ph='12')
        self._enviar(arcilla='140')
        self._enviar(ph='1.5')
        self.assertEqual(AnalisisSuelo.objects.count(), 0)

    def test_rechaza_fecha_futura(self):
        r = self._enviar(fecha=date.today().replace(year=date.today().year + 1).isoformat())
        self.assertContains(r, 'no puede ser futura')
        self.assertEqual(AnalisisSuelo.objects.count(), 0)

    def test_el_mas_reciente_aparece_primero(self):
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2024, 1, 5), ph=5.0)
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2026, 1, 5), ph=7.0)
        self.assertEqual(self.parcela.analisis.first().ph, 7.0)

    def test_otro_usuario_no_ve_ni_agrega_ni_quita(self):
        a = AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2025, 1, 5), ph=6.5)
        self.client.logout()
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'fecha': date.today().isoformat(), 'ph': '7'}).status_code, 404)
        borrar = reverse('parcelas:suelo_eliminar', args=[self.parcela.pk, a.pk])
        self.assertEqual(self.client.post(borrar).status_code, 404)
        self.assertEqual(AnalisisSuelo.objects.count(), 1)

    def test_quitar_solo_por_post(self):
        a = AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2025, 1, 5), ph=6.5)
        borrar = reverse('parcelas:suelo_eliminar', args=[self.parcela.pk, a.pk])
        self.assertEqual(self.client.get(borrar).status_code, 405)
        self.client.post(borrar)
        self.assertEqual(AnalisisSuelo.objects.count(), 0)

    def test_se_borra_con_la_parcela(self):
        AnalisisSuelo.objects.create(parcela=self.parcela, fecha=date(2025, 1, 5), ph=6.5)
        self.parcela.delete()
        self.assertEqual(AnalisisSuelo.objects.count(), 0)
        

# ---------- SINCRONIZACIÓN SIN CONEXIÓN (RF-0015 · CP-016) ----------
class SincronizacionTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, crear_distrito())
        self.papa = crear_cultivo('Papa', codigo='1001')
        self.maiz = crear_cultivo('Maiz', codigo='1002')
        self.campana = _campanas_anteriores()[0][0]
        self.url = reverse('parcelas:sincronizar')
        self.client.force_login(self.usuario)

    def _historial(self, cultivo=None, identificador=None, **extra):
        return {'tipo': 'historial', 'uuid': str(identificador or uuid.uuid4()), 'parcela': self.parcela.pk,
                'datos': {'campana_ini': str(self.campana), 'cultivo': str((cultivo or self.papa).pk),
                          'resultado': 'bueno'}, **extra}

    def _suelo(self, identificador=None, **datos):
        base = {'fecha': date.today().isoformat(), 'ph': '6.8', 'arcilla': '22', 'laboratorio': ''}
        base.update(datos)
        return {'tipo': 'suelo', 'uuid': str(identificador or uuid.uuid4()), 'parcela': self.parcela.pk,
                'datos': base}

    def _enviar(self, carga, cliente=None):
        return (cliente or self.client).post(self.url, json.dumps(carga), content_type='application/json')

    # -- lo que debe guardarse
    def test_guarda_una_campana_con_su_identificador(self):
        carga = self._historial()
        r = self._enviar(carga)
        self.assertEqual((r.status_code, r.json()['estado']), (201, 'ok'))
        h = HistorialCampana.objects.get()
        self.assertEqual((h.parcela, h.cultivo, h.campana_ini, h.resultado), (self.parcela, self.papa, self.campana, 'bueno'))
        self.assertEqual(str(h.uuid), carga['uuid'])

    def test_guarda_un_analisis_de_suelo(self):
        r = self._enviar(self._suelo())
        self.assertEqual(r.status_code, 201)
        a = AnalisisSuelo.objects.get()
        self.assertEqual((a.ph, a.arcilla), (6.8, 22.0))

    # -- CP-016: sin pérdida y sin duplicados
    def test_reenviar_el_mismo_registro_no_lo_duplica(self):
        carga = self._historial()
        self.assertEqual(self._enviar(carga).status_code, 201)
        for _ in range(3):                                         # el celular reintenta varias veces
            r = self._enviar(carga)
            self.assertEqual((r.status_code, r.json()['estado']), (200, 'duplicado'))
        self.assertEqual(HistorialCampana.objects.count(), 1)

    def test_reenviar_un_analisis_de_suelo_no_lo_duplica(self):
        carga = self._suelo()
        self._enviar(carga)
        self._enviar(carga)
        self.assertEqual(AnalisisSuelo.objects.count(), 1)

    def test_varios_registros_distintos_se_guardan_todos(self):
        self._enviar(self._historial(self.papa))
        self._enviar(self._historial(self.maiz))
        self._enviar(self._suelo())
        self._enviar(self._suelo(ph='7.1'))
        self.assertEqual((HistorialCampana.objects.count(), AnalisisSuelo.objects.count()), (2, 2))

    def test_los_registros_hechos_en_la_web_no_chocan_entre_si(self):
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.papa, campana_ini=2020, resultado='bueno')
        HistorialCampana.objects.create(parcela=self.parcela, cultivo=self.maiz, campana_ini=2020, resultado='malo')
        self.assertEqual(HistorialCampana.objects.filter(uuid__isnull=True).count(), 2)

    # -- mismas reglas que la web
    def test_aplica_la_regla_de_no_repetir_cultivo_en_la_campana(self):
        self._enviar(self._historial(self.papa))
        r = self._enviar(self._historial(self.papa))               # otro identificador, mismo cultivo y campaña
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['estado'], 'invalido')
        self.assertIn('Ya registró ese cultivo', ' '.join(r.json()['errores']))
        self.assertEqual(HistorialCampana.objects.count(), 1)

    def test_rechaza_datos_invalidos_y_no_guarda_nada(self):
        r = self._enviar(self._suelo(ph='', arcilla=''))
        self.assertEqual(r.status_code, 422)
        self.assertIn('al menos el pH', ' '.join(r.json()['errores']))
        r = self._enviar(self._suelo(ph='15'))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(AnalisisSuelo.objects.count(), 0)

    # -- seguridad
    def test_sin_sesion_responde_401_y_no_redirige(self):
        self.client.logout()
        r = self._enviar(self._historial())
        self.assertEqual((r.status_code, r.json()['estado']), (401, 'sin_sesion'))
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_no_se_puede_registrar_en_la_parcela_de_otro(self):
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        ajena = crear_parcela(otro, self.parcela.distrito, nombre='Ajena')
        carga = self._historial()
        carga['parcela'] = ajena.pk
        self.assertEqual(self._enviar(carga).status_code, 404)
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_el_identificador_de_otro_usuario_no_revela_nada(self):
        ajeno = uuid.uuid4()
        otro = self.crear_usuario(nombre='Otro', celular='912345678')
        HistorialCampana.objects.create(parcela=crear_parcela(otro, self.parcela.distrito, nombre='Ajena'),
                                        cultivo=self.maiz, campana_ini=2020, resultado='bueno', uuid=ajeno)
        r = self._enviar(self._historial(identificador=ajeno))
        self.assertEqual(r.status_code, 422)                       # no dice "duplicado": no confirma que existe
        self.assertEqual(HistorialCampana.objects.filter(parcela=self.parcela).count(), 0)

    def test_exige_token_csrf(self):
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.usuario)
        self.assertEqual(self._enviar(self._historial(), cliente=estricto).status_code, 403)
        self.assertEqual(HistorialCampana.objects.count(), 0)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_solicitudes_mal_formadas_responden_400(self):
        malas = [{'tipo': 'otro', 'uuid': str(uuid.uuid4()), 'parcela': 1, 'datos': {}},
                 {**self._historial(), 'uuid': 'no-es-un-uuid'},
                 {**self._historial(), 'parcela': 'x'},
                 {**self._historial(), 'datos': 'texto'},
                 {'tipo': 'historial'}]
        for carga in malas:
            self.assertEqual(self._enviar(carga).status_code, 400, carga)
        r = self.client.post(self.url, 'esto no es json', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(HistorialCampana.objects.count() + AnalisisSuelo.objects.count(), 0)