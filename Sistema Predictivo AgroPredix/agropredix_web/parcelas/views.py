from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import HistorialCampanaForm, ParcelaForm
from .models import Distrito, HistorialCampana, Parcela

from django.conf import settings

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
        messages.success(self.request, 'Su parcela fue guardada.')
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