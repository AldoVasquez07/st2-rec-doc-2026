from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import ParcelaForm
from .models import Distrito, Parcela


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