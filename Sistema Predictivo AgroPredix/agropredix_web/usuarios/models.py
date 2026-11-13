from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from . import roles
from .utils import normalizar_celular


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, nombre, password, correo, celular, **extra):
        correo = self.normalize_email(correo).lower() if correo else None
        celular = normalizar_celular(celular) if celular else None
        if not (correo or celular):
            raise ValueError('Se necesita un correo o un celular.')
        user = self.model(nombre=nombre, correo=correo, celular=celular, **extra)
        user.set_password(password)          # se guarda cifrada (hash), nunca en claro
        user.save(using=self._db)
        return user

    def create_user(self, nombre, password=None, correo=None, celular=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._crear(nombre, password, correo, celular, **extra)

    def create_superuser(self, correo, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('rol', roles.ADMINISTRADOR)
        nombre = extra.pop('nombre', 'Administrador')
        return self._crear(nombre, password, correo, None, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    nombre = models.CharField(max_length=150)
    correo = models.EmailField(unique=True, null=True, blank=True)
    celular = models.CharField(max_length=9, unique=True, null=True, blank=True)
    rol = models.CharField(max_length=20, choices=roles.ROLES, default=roles.AGRICULTOR)
    is_active = models.BooleanField('activo', default=True, db_column='activo')
    is_staff = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()
    USERNAME_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombre']

    def clean(self):
        super().clean()
        if not (self.correo or self.celular):
            raise ValidationError('Debe indicar un celular o un correo.')

    def save(self, *args, **kwargs):
        self.correo = self.correo.strip().lower() if self.correo else None
        self.celular = normalizar_celular(self.celular) if self.celular else None
        super().save(*args, **kwargs)

    def get_username(self):
        return self.correo or self.celular

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre.split()[0] if self.nombre else ''

    def __str__(self):
        return self.nombre


class RegistroAcceso(models.Model):
    """Auditoría de ingresos y salidas (igual que en sistema_salud)."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='accesos')
    accion = models.CharField(max_length=10)          # login / logout
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    duracion_sesion = models.DurationField(null=True, blank=True)

    def __str__(self):
        return f'{self.usuario} - {self.accion} - {self.fecha:%Y-%m-%d %H:%M}'