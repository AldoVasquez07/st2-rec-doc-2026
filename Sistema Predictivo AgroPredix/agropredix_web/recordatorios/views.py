import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import PreferenciasForm
from .models import Recordatorio, SuscripcionPush
from .servicio import preferencias_de


@login_required
def lista(request):
    items = list(Recordatorio.objects.filter(usuario=request.user)[:50])
    Recordatorio.objects.filter(usuario=request.user, leido=False).update(leido=True)
    return render(request, 'recordatorios/lista.html', {'recordatorios': items})


@login_required
@require_http_methods(['GET', 'POST'])
def preferencias(request):
    form = PreferenciasForm(request.POST or None, instance=preferencias_de(request.user))
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Sus preferencias de avisos fueron guardadas.')
        return redirect('recordatorios:preferencias')
    return render(request, 'recordatorios/preferencias.html',
                  {'form': form, 'vapid_public': settings.VAPID_PUBLIC_KEY})


@login_required
@require_POST
def suscribir(request):
    try:
        d = json.loads(request.body)
        endpoint, p256dh, auth = d['endpoint'], d['p256dh'], d['auth']
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False}, status=400)
    SuscripcionPush.objects.update_or_create(
        endpoint=endpoint, defaults={'usuario': request.user, 'p256dh': p256dh, 'auth': auth})
    return JsonResponse({'ok': True})