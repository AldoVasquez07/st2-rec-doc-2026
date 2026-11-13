from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Distrito(models.Model):
    ubigeo = models.CharField(max_length=6, unique=True)   # '040101' (= COD_UBIGEO 40101 del SISAGRI)
    nombre = models.CharField(max_length=100)
    provincia = models.CharField(max_length=100)
    departamento = models.CharField(max_length=100, default='Arequipa')
    latitud = models.FloatField(null=True, blank=True)     # punto de referencia para centrar el mapa
    longitud = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['provincia', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.provincia})'


class Parcela(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='parcelas')
    distrito = models.ForeignKey(Distrito, on_delete=models.PROTECT, related_name='parcelas')
    nombre = models.CharField(max_length=100)
    area_ha = models.FloatField(validators=[MinValueValidator(0.01), MaxValueValidator(10000)])
    # Caja aproximada del departamento de Arequipa
    latitud = models.FloatField(validators=[MinValueValidator(-17.7), MaxValueValidator(-14.4)])
    longitud = models.FloatField(validators=[MinValueValidator(-75.2), MaxValueValidator(-70.7)])
    referencia = models.CharField(max_length=200, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['usuario', 'nombre'],
                                               name='parcela_nombre_unico_por_usuario')]

    def __str__(self):
        return f'{self.nombre} - {self.distrito.nombre}'