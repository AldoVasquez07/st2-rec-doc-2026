from django.core.management.base import BaseCommand

from clima import servicio


class Command(BaseCommand):
    help = ('Descarga el clima reciente de los distritos que tienen parcelas (RF-0010). '
            'Programarlo una vez al día (cron, Render Cron Job, etc.).')

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=servicio.DIAS_POR_DEFECTO,
                            help='Días a descargar la primera vez (por defecto %(default)s).')
        parser.add_argument('--todos', action='store_true',
                            help='Incluir también los distritos sin parcelas.')

    def handle(self, *args, **opciones):
        from parcelas.models import Distrito
        distritos = Distrito.objects.all() if opciones['todos'] else servicio.distritos_con_parcelas()
        ok = fallos = 0
        for d in distritos:
            n = servicio.actualizar_distrito(d, dias=opciones['dias'])
            if n is None:
                fallos += 1
                self.stderr.write(f'  {d.nombre}: la fuente no respondió (se conserva lo guardado)')
            else:
                ok += 1
                self.stdout.write(f'  {d.nombre}: {n} días')
        self.stdout.write(self.style.SUCCESS(f'Clima actualizado: {ok} distritos; sin respuesta: {fallos}.'))
