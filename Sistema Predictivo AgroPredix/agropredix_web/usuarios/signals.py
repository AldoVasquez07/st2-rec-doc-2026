from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone

from .models import RegistroAcceso
from .utils import get_client_ip


@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    if request is None:
        return
    registro = RegistroAcceso.objects.create(
        usuario=user, accion='login', ip=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''))
    request.session['registro_login_id'] = registro.id


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    if request is None or user is None:
        return
    duracion = None
    registro_id = request.session.get('registro_login_id')
    if registro_id:
        login = RegistroAcceso.objects.filter(pk=registro_id).first()
        if login:
            duracion = timezone.now() - login.fecha
    RegistroAcceso.objects.create(
        usuario=user, accion='logout', ip=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''), duracion_sesion=duracion)