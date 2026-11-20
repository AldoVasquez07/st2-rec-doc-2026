from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from alertas import servicio as alertas
from parcelas.models import Parcela

from . import servicio

RANGOS = (30, 90)


@login_required
@require_GET
def clima_parcela(request, pk):
    """Gráficos de temperatura, humedad y lluvia del distrito de la parcela, más sus alertas (RF-0010 y RF-0009)."""
    parcela = get_object_or_404(Parcela.objects.select_related('distrito'), pk=pk, usuario=request.user)
    try:
        dias = int(request.GET.get('dias', RANGOS[0]))
    except ValueError:
        dias = RANGOS[0]
    dias = dias if dias in RANGOS else RANGOS[0]

    registros = servicio.serie(parcela.distrito, dias)
    datos = {
        'fechas': [r.fecha.strftime('%d/%m') for r in registros],
        'temp_media': [r.temp_media for r in registros],
        'temp_max': [r.temp_max for r in registros],
        'temp_min': [r.temp_min for r in registros],
        'humedad': [r.humedad for r in registros],
        'precipitacion': [r.precipitacion for r in registros],
    }
    return render(request, 'clima/parcela.html', {
        'parcela': parcela, 'datos': datos, 'dias': dias, 'rangos': RANGOS,
        'estado': servicio.estado(parcela.distrito),
        'alertas': alertas.alertas_de_distrito(parcela.distrito),
    })
