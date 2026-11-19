from django.core.management.base import BaseCommand

from cultivos.models import Cultivo
from recomendaciones.motor.agropredix_motor import cargar_modelo
from recomendaciones.servicio import RUTA_MODELO

PERMANENTES = {'12010010000'}      # Alfalfa: se siembra una vez y se corta varios años


class Command(BaseCommand):
    help = ('Crea en el catálogo los cultivos que cubre el modelo de recomendación y que aún no existan. '
            'No modifica ni duplica los que ya están.')

    def handle(self, *args, **opts):
        creados = 0
        for codigo, datos in cargar_modelo(RUTA_MODELO)['cultivos'].items():
            if Cultivo.objects.filter(codigo=codigo).exists():
                continue
            if Cultivo.objects.filter(nombre=datos['nombre']).exists():
                self.stdout.write(self.style.WARNING(
                    f"{datos['nombre']}: ya existe en el catálogo con otro código; no se creó el código {codigo}."))
                continue
            Cultivo.objects.create(
                codigo=codigo, nombre=datos['nombre'], grupo=datos['tipo'], familia=datos['familia'],
                tipo='permanente' if codigo in PERMANENTES else 'transitorio',
                es_leguminosa=datos['familia'] == 'Fabaceae', activo=True)
            creados += 1
        self.stdout.write(self.style.SUCCESS(f'{creados} cultivos creados en el catálogo.'))