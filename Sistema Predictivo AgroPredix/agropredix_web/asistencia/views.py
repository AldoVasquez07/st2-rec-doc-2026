from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import SolicitudForm
from .models import SolicitudAsistencia


@login_required
def lista(request):
    solicitudes = SolicitudAsistencia.objects.filter(usuario=request.user).select_related('parcela')
    return render(request, 'asistencia/lista.html', {'solicitudes': solicitudes})


@login_required
@require_http_methods(['GET', 'POST'])
def nueva(request):
    inicial = {}
    if request.GET.get('parcela', '').isdigit():
        inicial['parcela'] = request.GET['parcela']
    form = SolicitudForm(request.POST or None, usuario=request.user, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        solicitud = form.save(commit=False)
        solicitud.usuario = request.user
        solicitud.save()
        messages.success(request, 'Su consulta fue enviada. Aquí verá la respuesta cuando esté lista.')
        return redirect('asistencia:detalle', pk=solicitud.pk)
    return render(request, 'asistencia/nueva.html', {'form': form})


@login_required
def detalle(request, pk):
    solicitud = get_object_or_404(SolicitudAsistencia.objects.select_related('parcela', 'recomendacion'),
                                  pk=pk, usuario=request.user)
    return render(request, 'asistencia/detalle.html', {'s': solicitud})
