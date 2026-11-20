from django.db import models

from parcelas.models import Distrito


class RegistroClima(models.Model):
    """Un día de clima de un distrito (RF-0010). Se guarda para poder mostrarlo aunque la fuente falle."""
    distrito = models.ForeignKey(Distrito, on_delete=models.CASCADE, related_name='registros_clima')
    fecha = models.DateField()
    temp_media = models.FloatField(null=True, blank=True)        # °C
    temp_max = models.FloatField(null=True, blank=True)          # °C
    temp_min = models.FloatField(null=True, blank=True)          # °C
    humedad = models.FloatField(null=True, blank=True)           # % de humedad relativa
    precipitacion = models.FloatField(null=True, blank=True)     # mm en el día
    fuente = models.CharField(max_length=40, default='NASA POWER')

    class Meta:
        ordering = ['fecha']
        constraints = [models.UniqueConstraint(fields=['distrito', 'fecha'], name='clima_unico_por_dia')]

    def __str__(self):
        return f'{self.distrito.nombre} {self.fecha:%d/%m/%Y}'


class ActualizacionClima(models.Model):
    """Bitácora de cada intento de descarga: permite avisar al agricultor cuando la fuente no respondió."""
    distrito = models.ForeignKey(Distrito, on_delete=models.CASCADE, related_name='actualizaciones_clima')
    fecha = models.DateTimeField(auto_now_add=True)
    exito = models.BooleanField()
    registros = models.PositiveIntegerField(default=0)
    mensaje = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name_plural = 'actualizaciones de clima'

    def __str__(self):
        return f'{self.distrito.nombre} {self.fecha:%d/%m/%Y %H:%M} ({"ok" if self.exito else "falló"})'
