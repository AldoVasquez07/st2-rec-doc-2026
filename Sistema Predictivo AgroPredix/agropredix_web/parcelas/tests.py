import csv
import os
import tempfile
from datetime import date
from io import StringIO
from unittest import mock, skipUnless

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from cultivos.models import Cultivo
from usuarios.base_pruebas import PruebaBase

from .forms import _campanas_anteriores
from .models import Distrito, HistorialCampana, Parcela


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
    def test_archivo_real_trae_101_distritos(self):
        call_command('cargar_distritos', str(RUTA_DISTRITOS), stdout=StringIO())
        self.assertEqual(Distrito.objects.count(), 101)


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