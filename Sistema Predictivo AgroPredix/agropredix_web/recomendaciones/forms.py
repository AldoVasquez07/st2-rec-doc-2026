from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError

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