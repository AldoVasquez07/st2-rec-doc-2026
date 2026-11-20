from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from parcelas.models import Distrito

from . import servicio


@login_required
@require_GET
def zona(request):
    mis_distritos = list(Distrito.objects.filter(parcelas__usuario=request.user).distinct())
    if not mis_distritos:
        messages.info(request, 'Registre una parcela para ver los reportes de su zona.')
        return redirect('parcelas:crear')
    elegido = mis_distritos[0]
    if request.GET.get('distrito', '').isdigit():
        elegido = next((d for d in mis_distritos if d.pk == int(request.GET['distrito'])), elegido)
    return render(request, 'reportes/zona.html',
                  {'distrito': elegido, 'mis_distritos': mis_distritos, **servicio.reporte_zona(elegido)})