from django import forms

from recomendaciones.models import Recomendacion

from .models import SolicitudAsistencia


class SolicitudForm(forms.ModelForm):
    class Meta:
        model = SolicitudAsistencia
        fields = ['parcela', 'recomendacion', 'descripcion']
        labels = {'parcela': 'Parcela (opcional)', 'recomendacion': 'Recomendación que quiere que revisen (opcional)',
                  'descripcion': '¿Qué duda tiene?'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 5, 'maxlength': 1000,
                                                       'placeholder': 'Cuéntenos con sus palabras qué le preocupa.'})}

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parcela'].queryset = usuario.parcelas.all()
        self.fields['recomendacion'].queryset = (Recomendacion.objects.filter(parcela__usuario=usuario)
                                                 .select_related('parcela'))
        self.fields['recomendacion'].label_from_instance = (
            lambda r: f'{r.parcela.nombre} · {r.fecha:%d/%m/%Y}')
        for campo in ('parcela', 'recomendacion'):
            self.fields[campo].required = False
            self.fields[campo].widget.attrs['class'] = 'form-select'
        self.fields['descripcion'].widget.attrs['class'] = 'form-control'

    def clean_descripcion(self):
        texto = self.cleaned_data['descripcion'].strip()
        if len(texto) < 10:
            raise forms.ValidationError('Cuéntenos un poco más para poder ayudarle.')
        return texto
