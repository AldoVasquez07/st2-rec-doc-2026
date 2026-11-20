from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from cultivos.models import Cultivo
from usuarios.forms import EstiloBootstrapMixin
from .geografia import distrito_mas_cercano
from .models import AnalisisSuelo, Distrito, HistorialCampana, Parcela


class ParcelaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Parcela
        fields = ['nombre', 'distrito', 'area_ha', 'latitud', 'longitud', 'referencia']
        labels = {'nombre': 'Nombre de su parcela', 'area_ha': 'Tamaño aproximado (hectáreas)',
                  'latitud': 'Latitud', 'longitud': 'Longitud', 'referencia': 'Referencia (opcional)'}
        help_texts = {'area_ha': 'Un dato aproximado basta. 1 hectárea = 10 000 m².',
                      'distrito': 'Opcional: si lo deja en blanco, lo detectamos con el punto que marque en el mapa.'}
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
        self.fields['distrito'].empty_label = 'Detectar con el mapa'
        self.fields['distrito'].required = False

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        repetidas = Parcela.objects.filter(usuario=self.usuario, nombre__iexact=nombre)
        if self.instance.pk:
            repetidas = repetidas.exclude(pk=self.instance.pk)
        if repetidas.exists():
            raise ValidationError('Ya tiene una parcela con ese nombre.')
        return nombre
    
    def clean(self):
        datos = super().clean()
        lat, lon = datos.get('latitud'), datos.get('longitud')
        if not datos.get('distrito') and lat is not None and lon is not None:
            detectado = distrito_mas_cercano(lat, lon)
            if detectado is None:
                self.add_error('distrito', 'No pudimos ubicar su distrito con el mapa. Elíjalo de la lista.')
            else:
                datos['distrito'] = detectado
        return datos


def _campanas_anteriores():
    hoy = date.today()
    actual = hoy.year if hoy.month >= 8 else hoy.year - 1   # la campaña agrícola empieza en agosto
    return [(a, f'{a}-{a + 1}') for a in range(actual - 1, actual - 11, -1)]


class HistorialCampanaForm(EstiloBootstrapMixin, forms.ModelForm):
    campana_ini = forms.TypedChoiceField(label='Campaña', coerce=int, choices=[])

    class Meta:
        model = HistorialCampana
        fields = ['campana_ini', 'cultivo', 'resultado']
        labels = {'cultivo': '¿Qué sembró?', 'resultado': '¿Cómo le fue?'}

    def __init__(self, *args, parcela=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.parcela = parcela
        self.fields['campana_ini'].choices = [('', 'Elija la campaña')] + _campanas_anteriores()
        self.fields['cultivo'].queryset = Cultivo.objects.filter(activo=True)
        self.fields['cultivo'].empty_label = 'Elija el cultivo'
        self.fields['resultado'].choices = [('', 'Elija una opción')] + list(
            HistorialCampana.Resultado.choices)

    def clean(self):
        datos = super().clean()
        campana, cultivo = datos.get('campana_ini'), datos.get('cultivo')
        if campana and cultivo:
            repetidos = HistorialCampana.objects.filter(
                parcela=self.parcela, campana_ini=campana, cultivo=cultivo)
            if self.instance.pk:
                repetidos = repetidos.exclude(pk=self.instance.pk)
            if repetidos.exists():
                raise ValidationError('Ya registró ese cultivo en esa campaña.')
        return datos
    

class AnalisisSueloForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = AnalisisSuelo
        fields = ['fecha', 'ph', 'arcilla', 'laboratorio']
        labels = {'fecha': 'Fecha del análisis', 'ph': 'pH del suelo', 'arcilla': 'Arcilla (%)',
                  'laboratorio': 'Laboratorio (opcional)'}
        help_texts = {'ph': 'Aparece en su informe como «pH». Debe estar entre 3 y 10.',
                      'arcilla': 'Porcentaje de arcilla de la textura. Si su informe no lo trae, déjelo en blanco.'}
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'ph': forms.NumberInput(attrs={'step': '0.1', 'min': '3', 'max': '10'}),
            'arcilla': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '100'}),
            'laboratorio': forms.TextInput(attrs={'placeholder': 'Ej.: Laboratorio de la universidad'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha'].widget.attrs['max'] = date.today().isoformat()

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if fecha > date.today():
            raise ValidationError('La fecha del análisis no puede ser futura.')
        return fecha