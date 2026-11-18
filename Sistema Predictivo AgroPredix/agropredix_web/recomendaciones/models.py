from django.db import models

from parcelas.models import Parcela


class Recomendacion(models.Model):
    """Cada recomendación generada queda guardada (RF-0007)."""
    parcela = models.ForeignKey(Parcela, on_delete=models.CASCADE, related_name='recomendaciones')
    mes = models.PositiveSmallIntegerField()                 # mes de siembra consultado (1-12)
    antecesor = models.CharField(max_length=100, blank=True)  # cultivo anterior usado (vacío = sin registrar)
    resultado = models.JSONField()                           # ranking completo con explicaciones
    suelo = models.JSONField(default=dict, blank=True)       # pH/arcilla usados y si vienen de su análisis
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.parcela.nombre} - mes {self.mes} ({self.fecha:%d/%m/%Y})'