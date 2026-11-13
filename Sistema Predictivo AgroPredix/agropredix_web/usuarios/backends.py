from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .utils import normalizar_celular


class IdentificadorBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        Usuario = get_user_model()
        ident = username.strip()
        if '@' in ident:
            filtro = Q(correo__iexact=ident)
        else:
            celular = normalizar_celular(ident)
            if not celular:
                return None
            filtro = Q(celular=celular)
        try:
            user = Usuario.objects.get(filtro)
        except Usuario.DoesNotExist:
            Usuario().set_password(password)      # mismo tiempo de respuesta si no existe
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None