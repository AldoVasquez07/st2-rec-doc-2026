from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import Usuario
from .utils import normalizar_celular


class EstiloBootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, forms.Select):
                clase = 'form-select'
            elif isinstance(w, forms.CheckboxInput):
                clase = 'form-check-input'
            else:
                clase = 'form-control'
            w.attrs['class'] = f"{w.attrs.get('class', '')} {clase}".strip()


class LoginForm(EstiloBootstrapMixin, AuthenticationForm):
    username = forms.CharField(
        label='Celular o correo',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username',
                                      'placeholder': '987654321 o nombre@correo.com'}))
    password = forms.CharField(
        label='Contraseña', strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    error_messages = {
        'invalid_login': 'El celular, el correo o la contraseña no son correctos.',
        'inactive': 'Esta cuenta está desactivada.',
    }


def separar_identificador(valor):
    """'correo@x.com' -> (correo, None) | '987 654 321' -> (None, '987654321')."""
    valor = valor.strip()
    if '@' in valor:
        validate_email(valor)
        return valor.lower(), None
    celular = normalizar_celular(valor)
    if not celular:
        raise ValidationError('Escriba un celular de 9 dígitos que empiece con 9, o un correo válido.')
    return None, celular


class RegistroForm(EstiloBootstrapMixin, forms.Form):
    """RF-0001: solo pide celular o correo, nombre y contraseña."""
    nombre = forms.CharField(label='Su nombre', max_length=150)
    identificador = forms.CharField(label='Celular o correo')
    password1 = forms.CharField(label='Contraseña', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Repita la contraseña', strip=False,
                                widget=forms.PasswordInput)

    def clean_identificador(self):
        valor = self.cleaned_data['identificador']
        correo, celular = separar_identificador(valor)
        if correo and Usuario.objects.filter(correo__iexact=correo).exists():
            raise ValidationError('Ya existe una cuenta con ese correo.')
        if celular and Usuario.objects.filter(celular=celular).exists():
            raise ValidationError('Ya existe una cuenta con ese celular.')
        return valor

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get('password1'), datos.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error('password1', e)
        return datos

    def save(self):
        correo, celular = separar_identificador(self.cleaned_data['identificador'])
        return Usuario.objects.create_user(
            nombre=self.cleaned_data['nombre'].strip(),
            password=self.cleaned_data['password1'],
            correo=correo, celular=celular)


class PerfilForm(EstiloBootstrapMixin, forms.ModelForm):
    celular = forms.CharField(label='Celular', required=False)   # sin max_length: se normaliza en clean_celular

    class Meta:
        model = Usuario
        fields = ['nombre', 'correo', 'celular']

    def clean_correo(self):
        return (self.cleaned_data.get('correo') or '').strip().lower() or None

    def clean_celular(self):
        valor = self.cleaned_data.get('celular')
        if not valor:
            return None
        celular = normalizar_celular(valor)
        if not celular:
            raise ValidationError('Escriba un celular de 9 dígitos que empiece con 9.')
        return celular

    def clean(self):
        datos = super().clean()
        if not datos.get('correo') and not datos.get('celular'):
            raise ValidationError('Debe dejar al menos un celular o un correo.')
        return datos


class CambiarClaveForm(EstiloBootstrapMixin, PasswordChangeForm):
    """Pide la clave anterior (criterio de HU-0015)."""