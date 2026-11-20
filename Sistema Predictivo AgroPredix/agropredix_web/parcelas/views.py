from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AnalisisSueloForm, HistorialCampanaForm, ParcelaForm
from .models import AnalisisSuelo, Distrito, HistorialCampana, Parcela

from django.conf import settings

import json
import uuid as uuidlib

from django.db import IntegrityError, transaction
from django.http import JsonResponse

class PropietarioMixin(LoginRequiredMixin):
    """Cada agricultor solo ve y toca sus propias parcelas (RF-0002)."""
    model = Parcela

    def get_queryset(self):
        return Parcela.objects.filter(usuario=self.request.user).select_related('distrito')


class FormularioParcelaMixin(PropietarioMixin):
    form_class = ParcelaForm
    template_name = 'parcelas/parcela_form.html'
    success_url = reverse_lazy('parcelas:lista')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['usuario'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['centros'] = {d.pk: [d.latitud, d.longitud]
                          for d in Distrito.objects.exclude(latitud__isnull=True)}
        ctx['google_maps'] = {'key': settings.GOOGLE_MAPS_API_KEY,
                              'mapId': settings.GOOGLE_MAPS_MAP_ID}
        return ctx

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, f'Su parcela fue guardada en el distrito de {form.cleaned_data["distrito"].nombre}.')
        return super().form_valid(form)


class ParcelaListView(PropietarioMixin, ListView):
    template_name = 'parcelas/parcela_list.html'
    context_object_name = 'parcelas'


class ParcelaCreateView(FormularioParcelaMixin, CreateView):
    pass


class ParcelaUpdateView(FormularioParcelaMixin, UpdateView):
    pass


class ParcelaDeleteView(PropietarioMixin, DeleteView):
    template_name = 'parcelas/parcela_confirm_delete.html'
    success_url = reverse_lazy('parcelas:lista')

    def form_valid(self, form):
        messages.success(self.request, 'Su parcela fue eliminada.')
        return super().form_valid(form)
    


@login_required
def historial(request, pk):
    parcela = get_object_or_404(Parcela, pk=pk, usuario=request.user)   # de otro usuario: 404
    form = HistorialCampanaForm(request.POST or None, parcela=parcela)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        registro.parcela = parcela
        registro.save()
        messages.success(request, 'Se guardó la campaña.')
        return redirect('parcelas:historial', pk=parcela.pk)
    return render(request, 'parcelas/historial.html', {
        'parcela': parcela, 'form': form,
        'registros': parcela.historial.select_related('cultivo')})


@login_required
@require_POST
def historial_eliminar(request, pk, hpk):
    registro = get_object_or_404(HistorialCampana, pk=hpk, parcela__pk=pk,
                                 parcela__usuario=request.user)
    registro.delete()
    messages.success(request, 'Se quitó la campaña del historial.')
    return redirect('parcelas:historial', pk=pk)


@login_required
def suelo(request, pk):
    parcela = get_object_or_404(Parcela, pk=pk, usuario=request.user)   # de otro usuario: 404
    form = AnalisisSueloForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        registro.parcela = parcela
        registro.save()
        messages.success(request, 'Se guardó su análisis de suelo.')
        return redirect('parcelas:suelo', pk=parcela.pk)
    return render(request, 'parcelas/suelo.html', {
        'parcela': parcela, 'form': form, 'registros': parcela.analisis.all()})


@login_required
@require_POST
def suelo_eliminar(request, pk, spk):
    registro = get_object_or_404(AnalisisSuelo, pk=spk, parcela__pk=pk, parcela__usuario=request.user)
    registro.delete()
    messages.success(request, 'Se quitó el análisis de suelo.')
    return redirect('parcelas:suelo', pk=pk)


# ---------- SINCRONIZACIÓN DE REGISTROS HECHOS SIN CONEXIÓN (RF-0015, CP-016) ----------
TIPOS_SINCRONIZABLES = {
    'historial': (HistorialCampana, HistorialCampanaForm),
    'suelo': (AnalisisSuelo, AnalisisSueloForm),
}


def _mensajes_de_error(form):
    mensajes = []
    for campo, errores in form.errors.items():
        etiqueta = '' if campo == '__all__' else f'{form.fields[campo].label or campo}: '
        mensajes += [f'{etiqueta}{e}' for e in errores]
    return mensajes


@require_POST
def sincronizar(request):
    """Recibe un registro que el celular guardó sin conexión.

    Es idempotente: el mismo 'uuid' nunca se guarda dos veces, así que si la respuesta se pierde
    y el celular reintenta, el registro no se duplica. Usa los mismos formularios (y reglas) que la web.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'estado': 'sin_sesion'}, status=401)
    try:
        carga = json.loads(request.body)
        modelo, formulario = TIPOS_SINCRONIZABLES[carga['tipo']]
        identificador = uuidlib.UUID(str(carga['uuid']))
        parcela_id = int(carga['parcela'])
        datos = carga['datos']
        if not isinstance(datos, dict):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'estado': 'invalido', 'errores': ['La solicitud no es válida.']}, status=400)

    parcela = Parcela.objects.filter(pk=parcela_id, usuario=request.user).first()
    if parcela is None:
        return JsonResponse({'estado': 'rechazado', 'errores': ['La parcela no existe o no es suya.']}, status=404)

    ya_guardado = modelo.objects.filter(uuid=identificador, parcela__usuario=request.user)
    if ya_guardado.exists():                                  # reintento de algo que sí llegó
        return JsonResponse({'estado': 'duplicado'})

    form = formulario(datos, **({'parcela': parcela} if modelo is HistorialCampana else {}))
    if not form.is_valid():
        return JsonResponse({'estado': 'invalido', 'errores': _mensajes_de_error(form)}, status=422)
    try:
        with transaction.atomic():
            registro = form.save(commit=False)
            registro.parcela = parcela
            registro.uuid = identificador
            registro.save()
    except IntegrityError:                                    # dos envíos a la vez, o restricción única
        if ya_guardado.exists():
            return JsonResponse({'estado': 'duplicado'})
        return JsonResponse({'estado': 'invalido', 'errores': ['Ya existe un registro igual.']}, status=422)
    return JsonResponse({'estado': 'ok', 'id': registro.pk}, status=201)