import csv

from django.core.management.base import BaseCommand

from parcelas.models import Distrito


class Command(BaseCommand):
    help = 'Carga los distritos de Arequipa desde coordenadas_distritos.csv'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')

    def handle(self, *args, **opts):
        total = 0
        with open(opts['csv_path'], encoding='utf-8-sig', newline='') as f:
            for fila in csv.DictReader(f):
                lat, lon = fila.get('latitud'), fila.get('longitud')
                Distrito.objects.update_or_create(
                    ubigeo=str(int(float(fila['cod_ubigeo']))).zfill(6),
                    defaults=dict(
                        nombre=fila['distrito'].title(),
                        provincia=fila['provincia'].title(),
                        latitud=float(lat) if lat else None,
                        longitud=float(lon) if lon else None))
                total += 1
        self.stdout.write(self.style.SUCCESS(f'{total} distritos cargados.'))