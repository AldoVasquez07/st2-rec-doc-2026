from django.core.management.base import BaseCommand

from recordatorios import servicio


class Command(BaseCommand):
    help = 'Genera y envía los recordatorios de siembra y cosecha. Programar una vez al día.'

    def handle(self, *args, **opciones):
        nuevos = servicio.generar()
        enviados = servicio.enviar_pendientes()
        self.stdout.write(self.style.SUCCESS(f'Recordatorios nuevos: {len(nuevos)}; enviados: {enviados}.'))