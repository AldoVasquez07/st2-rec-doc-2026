from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError
from cultivos.models import Cultivo
from .models import Siembra


class SiembraForm(forms.Form):
    fecha_siembra = forms.DateField(
        label='¿Cuándo sembró o piensa sembrar?', widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    cierre_estimado = forms.DateField(
        required=False, label='¿Cuándo piensa cosechar? (opcional)',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    def clean_fecha_siembra(self):
        fecha = self.cleaned_data['fecha_siembra']
        hoy = date.today()
        if not hoy - timedelta(days=365) <= fecha <= hoy + timedelta(days=365):
            raise ValidationError('La fecha debe estar dentro de un año antes o después de hoy.')
        return fecha

    def clean(self):
        datos = super().clean()
        siembra, cierre = datos.get('fecha_siembra'), datos.get('cierre_estimado')
        if siembra and cierre:
            if cierre <= siembra:
                self.add_error('cierre_estimado', 'La cosecha debe ser después de la siembra.')
            elif cierre > siembra + timedelta(days=1100):
                self.add_error('cierre_estimado', 'Esa fecha está demasiado lejos de la siembra.')
        return datos


class ValoracionForm(forms.Form):
    resultado = forms.ChoiceField(
        label='¿Cómo le fue con este cultivo?', choices=Siembra.Resultado.choices, widget=forms.RadioSelect)
    comentario = forms.CharField(
        required=False, max_length=300, label='Comentario (opcional)',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'maxlength': 300,
                                     'placeholder': 'Ej.: hubo mucha plaga, el agua llegó tarde...'}))


class PreguntasForm(forms.Form):
    """Preguntas opcionales en lenguaje cotidiano para afinar la recomendación (RF-0004)."""
    TIERRA = [
        ('', 'No sé / prefiero no responder'),
        ('suelta', 'Suelta: se desmorona y el agua se filtra rápido'),
        ('media', 'Normal: se puede amasar y el agua baja con calma'),
        ('pesada', 'Pesada: se pega, hace barro y el agua se empoza'),
    ]
    tierra = forms.ChoiceField(required=False, choices=TIERRA, label='¿Cómo es la tierra de su chacra?',
                               widget=forms.Select(attrs={'class': 'form-select'}))
    ultimo_cultivo = forms.ModelChoiceField(
        required=False, queryset=Cultivo.objects.filter(activo=True), empty_label='No recuerdo / no sembré',
        label='¿Qué sembró la última vez en esta parcela?', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, preguntar_cultivo=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not preguntar_cultivo:       # si ya tiene historial, no se le vuelve a preguntar
            del self.fields['ultimo_cultivo']