import csv
import os
import tempfile
from io import StringIO
from unittest import skipUnless

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Cultivo

RUTA_REAL = settings.BASE_DIR / 'datos' / 'sisagri_campana.csv'
COLUMNAS = ['cod_producto', 'producto', 'grupo', 'tipo_cultivo', 'familia', 'es_leguminosa']
FILAS = [
    ['14030010000', 'ACELGA', 'hortaliza', 'transitorio', 'Amaranthaceae', 'False'],
    ['14030010000', 'ACELGA', 'hortaliza', 'transitorio', 'Amaranthaceae', 'False'],   # otra campaña: repetida
    ['12010010000.0', 'ALFALFA', 'pasto_cultivado', 'pasto', 'Fabaceae', 'True'],
    ['15010010000', 'PALTO', 'frutal', 'permanente', '', 'False'],                     # sin familia
]


def escribir_csv(carpeta):
    ruta = os.path.join(carpeta, 'campana.csv')
    with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUMNAS)
        escritor.writerows(FILAS)
    return ruta


class CargaCultivosTests(TestCase):
    def test_carga_desde_csv_sin_repetir_cultivos(self):
        salida = StringIO()
        with tempfile.TemporaryDirectory() as carpeta:
            call_command('cargar_cultivos', escribir_csv(carpeta), stdout=salida)
        self.assertEqual(Cultivo.objects.count(), 3)
        self.assertIn('3 cultivos cargados', salida.getvalue())
        alfalfa = Cultivo.objects.get(nombre='Alfalfa')
        self.assertTrue(alfalfa.es_leguminosa)
        self.assertEqual(alfalfa.codigo, '12010010000')
        self.assertEqual(Cultivo.objects.get(nombre='Palto').familia, '')

    def test_cargar_dos_veces_no_duplica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = escribir_csv(carpeta)
            call_command('cargar_cultivos', ruta, stdout=StringIO())
            call_command('cargar_cultivos', ruta, stdout=StringIO())
        self.assertEqual(Cultivo.objects.count(), 3)

    @skipUnless(RUTA_REAL.exists(), 'falta datos/sisagri_campana.csv')
    def test_archivo_real_trae_95_cultivos(self):
        call_command('cargar_cultivos', str(RUTA_REAL), stdout=StringIO())
        self.assertEqual(Cultivo.objects.count(), 95)
        self.assertTrue(Cultivo.objects.filter(es_leguminosa=True).exists())


class ModeloCultivoTests(TestCase):
    def test_orden_alfabetico_y_texto(self):
        Cultivo.objects.create(codigo='2', nombre='Zanahoria', grupo='hortaliza', tipo='transitorio')
        Cultivo.objects.create(codigo='1', nombre='Ajo', grupo='hortaliza', tipo='transitorio')
        self.assertEqual(list(Cultivo.objects.values_list('nombre', flat=True)), ['Ajo', 'Zanahoria'])
        self.assertEqual(str(Cultivo.objects.get(nombre='Ajo')), 'Ajo')

    def test_el_nombre_no_se_repite(self):
        Cultivo.objects.create(codigo='1', nombre='Ajo', grupo='hortaliza', tipo='transitorio')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cultivo.objects.create(codigo='2', nombre='Ajo', grupo='hortaliza', tipo='transitorio')