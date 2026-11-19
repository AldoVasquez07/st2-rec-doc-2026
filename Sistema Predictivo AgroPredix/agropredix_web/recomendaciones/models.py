from django.db import models
from parcelas.models import HistorialCampana, Parcela


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
    
    
class Siembra(models.Model):
    """El agricultor sigue una recomendación (siembra un cultivo) y, al cierre de la campaña, la valora (RF-0011)."""
    Resultado = HistorialCampana.Resultado          # bueno / regular / malo

    recomendacion = models.ForeignKey(Recomendacion, on_delete=models.CASCADE, related_name='siembras')
    cultivo_cod = models.CharField(max_length=20)    # código del cultivo en el modelo (= Cultivo.codigo)
    cultivo = models.CharField(max_length=100)       # nombre mostrado al agricultor
    # Lo que el motor había calculado: sirve después para contrastarlo con lo que pasó (ajuste de reglas)
    puesto = models.PositiveSmallIntegerField()
    idoneidad = models.FloatField()
    certeza_pct = models.FloatField()
    fecha_siembra = models.DateField()
    cierre_estimado = models.DateField()
    # Valoración post-campaña
    resultado = models.CharField(max_length=10, choices=Resultado.choices, blank=True)
    comentario = models.CharField(max_length=300, blank=True)
    fecha_valoracion = models.DateTimeField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['cierre_estimado']
        constraints = [models.UniqueConstraint(fields=['recomendacion', 'cultivo_cod'], name='una_siembra_por_cultivo_y_recomendacion')]

    @property
    def parcela(self):
        return self.recomendacion.parcela

    @property
    def valorada(self):
        return bool(self.resultado)

    def __str__(self):
        return f'{self.cultivo} en {self.parcela.nombre} (siembra {self.fecha_siembra:%d/%m/%Y})'