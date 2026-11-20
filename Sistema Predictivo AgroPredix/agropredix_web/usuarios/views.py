from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView, UpdateView
from alertas.servicio import alertas_de_usuario
from recomendaciones.seguimiento import pendientes_de_valorar
from recordatorios.models import Recordatorio
from django.contrib.auth import login, logout
from .forms import CambiarClaveForm, EliminarCuentaForm, LoginForm, PerfilForm, RegistroForm


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
    
    
class EliminarCuentaView(LoginRequiredMixin, FormView):
    template_name = 'usuarios/eliminar_cuenta.html'
    form_class = EliminarCuentaForm
    success_url = reverse_lazy('usuarios:login')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['usuario'] = self.request.user
        return kwargs

    def form_valid(self, form):
        usuario = self.request.user
        logout(self.request)        # registra la salida y limpia la sesión
        usuario.delete()            # borra también parcelas, recomendaciones, siembras, consultas y avisos
        messages.success(self.request, 'Su cuenta y todos sus datos fueron eliminados.')
        return super().form_valid(form)


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['parcelas'] = self.request.user.parcelas.select_related('distrito')[:5]
        ctx['pendientes_valoracion'] = list(pendientes_de_valorar(self.request.user)[:3])
        ctx['alertas'] = alertas_de_usuario(self.request.user)
        ctx['recordatorios'] = list(Recordatorio.objects.filter(usuario=self.request.user, leido=False)[:3])
        return ctx
    
