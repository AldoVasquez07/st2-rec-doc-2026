from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView, UpdateView

from .forms import CambiarClaveForm, LoginForm, PerfilForm, RegistroForm


class IngresarView(LoginView):
    template_name = 'usuarios/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


class RegistroView(FormView):
    template_name = 'usuarios/registro.html'
    form_class = RegistroForm
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        usuario = form.save()
        login(self.request, usuario, backend='usuarios.backends.IdentificadorBackend')
        messages.success(self.request, '¡Su cuenta fue creada! Ya puede registrar su parcela.')
        return super().form_valid(form)


class PerfilView(LoginRequiredMixin, UpdateView):
    form_class = PerfilForm
    template_name = 'usuarios/perfil.html'
    success_url = reverse_lazy('usuarios:perfil')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Sus datos fueron actualizados.')
        return super().form_valid(form)


class CambiarClaveView(LoginRequiredMixin, PasswordChangeView):
    form_class = CambiarClaveForm
    template_name = 'usuarios/cambiar_clave.html'
    success_url = reverse_lazy('usuarios:perfil')

    def form_valid(self, form):
        messages.success(self.request, 'Su contraseña fue cambiada.')
        return super().form_valid(form)


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['parcelas'] = self.request.user.parcelas.select_related('distrito')[:5]
        return ctx