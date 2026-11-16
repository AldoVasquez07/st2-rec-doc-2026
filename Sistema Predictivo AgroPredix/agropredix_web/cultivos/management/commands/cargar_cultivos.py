import csv

from django.core.management.base import BaseCommand

from cultivos.models import Cultivo


class Command(BaseCommand):
    help = 'Carga el catálogo de cultivos desde sisagri_campana.csv'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')

    def handle(self, *args, **opts):
        vistos = {}
        with open(opts['csv_path'], encoding='utf-8-sig', newline='') as f:
            for fila in csv.DictReader(f):
                vistos.setdefault(fila['producto'], fila)
        for nombre, fila in vistos.items():
            Cultivo.objects.update_or_create(
                codigo=str(int(float(fila['cod_producto']))),
                defaults=dict(
                    nombre=nombre.strip().title(),
                    grupo=fila['grupo'],
                    tipo=fila['tipo_cultivo'],
                    familia=(fila['familia'] or '').strip(),
                    es_leguminosa=fila['es_leguminosa'].strip().lower() == 'true'))
        self.stdout.write(self.style.SUCCESS(f'{len(vistos)} cultivos cargados.'))