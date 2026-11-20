from django import forms
from django.conf import settings

from usuarios.forms import EstiloBootstrapMixin

from .models import PreferenciaRecordatorio


class PreferenciasForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = PreferenciaRecordatorio
        fields = ['canal', 'avisar_siembra', 'avisar_cosecha', 'dias_antes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.SMS_HABILITADO:        # no se ofrece SMS hasta tener proveedor
            self.fields['canal'].choices = [c for c in PreferenciaRecordatorio.Canal.choices if c[0] != 'sms']