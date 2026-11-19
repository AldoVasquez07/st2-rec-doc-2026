from django.core.management.base import BaseCommand

from cultivos.models import Cultivo

# tengo que que confirmar con: fichas técnicas (INIA / MIDAGRI) y corríjalos en el admin (Cultivos). La alfalfa es perenne: se evalúa por año.
CICLOS_REFERENCIALES = {
    '14030100000': 180,   # Cebolla
    '14050060000': 110,   # Maiz Chala
    '14030030000': 170,   # Ajo
    '14040090000': 140,   # Papa
    '14030220000': 110,   # Zanahoria
    '14030050000': 100,   # Arveja Grano Verde
    '14030370000': 120,   # Haba Grano Verde
    '12010010000': 365,   # Alfalfa
    '14030060000': 120,   # Apio
    '14030360000': 80,    # Frijol Vainita
}


class Command(BaseCommand):
    help = 'Asigna la duración referencial del ciclo a los cultivos que aún no la tienen (usar --forzar para reemplazar).'

    def add_arguments(self, parser):
        parser.add_argument('--forzar', action='store_true', help='reemplaza también los valores ya cargados')

    def handle(self, *args, **opts):
        asignados = 0
        for codigo, dias in CICLOS_REFERENCIALES.items():
            cultivos = Cultivo.objects.filter(codigo=codigo)
            if not opts['forzar']:
                cultivos = cultivos.filter(ciclo_dias__isnull=True)
            asignados += cultivos.update(ciclo_dias=dias)
        self.stdout.write(self.style.SUCCESS(f'{asignados} cultivos con ciclo asignado.'))