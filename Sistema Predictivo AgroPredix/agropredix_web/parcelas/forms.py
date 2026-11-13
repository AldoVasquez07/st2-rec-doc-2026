from django import forms
from django.core.exceptions import ValidationError

from usuarios.forms import EstiloBootstrapMixin

from .models import Distrito, Parcela


class ParcelaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Parcela
        fields = ['nombre', 'distrito', 'area_ha', 'latitud', 'longitud', 'referencia']
        labels = {'nombre': 'Nombre de su parcela', 'area_ha': 'Tamaño aproximado (hectáreas)',
                  'latitud': 'Latitud', 'longitud': 'Longitud', 'referencia': 'Referencia (opcional)'}
        help_texts = {'area_ha': 'Un dato aproximado basta. 1 hectárea = 10 000 m².'}
        widgets = {
            'area_ha': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'latitud': forms.NumberInput(attrs={'readonly': True, 'step': 'any'}),
            'longitud': forms.NumberInput(attrs={'readonly': True, 'step': 'any'}),
            'referencia': forms.TextInput(attrs={'placeholder': 'Ej.: junto al canal, cerca de la escuela'}),
        }
        error_messages = {
            'latitud': {'required': 'Marque la ubicación de su parcela en el mapa.'},
            'longitud': {'required': 'Marque la ubicación de su parcela en el mapa.'},
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields['distrito'].queryset = Distrito.objects.all()
        self.fields['distrito'].empty_label = 'Elija su distrito'

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        repetidas = Parcela.objects.filter(usuario=self.usuario, nombre__iexact=nombre)
        if self.instance.pk:
            repetidas = repetidas.exclude(pk=self.instance.pk)
        if repetidas.exists():
            raise ValidationError('Ya tiene una parcela con ese nombre.')
        return nombre