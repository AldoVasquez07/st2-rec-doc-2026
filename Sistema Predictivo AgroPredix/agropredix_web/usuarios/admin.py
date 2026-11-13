from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import RegistroAcceso, Usuario


class UsuarioCreacionForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('nombre', 'correo', 'celular', 'rol')


class UsuarioCambioForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = '__all__'


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioCambioForm
    add_form = UsuarioCreacionForm
    ordering = ('-fecha_registro',)
    list_display = ('nombre', 'correo', 'celular', 'rol', 'is_active')
    list_filter = ('rol', 'is_active', 'is_staff')
    search_fields = ('nombre', 'correo', 'celular')
    fieldsets = (
        (None, {'fields': ('correo', 'celular', 'password')}),
        ('Datos', {'fields': ('nombre', 'rol')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser',
                                 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',),
                'fields': ('nombre', 'correo', 'celular', 'rol', 'password1', 'password2')}),
    )


admin.site.register(RegistroAcceso)