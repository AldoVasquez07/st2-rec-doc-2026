from django.db import models


class Cultivo(models.Model):
    codigo = models.CharField(max_length=20, unique=True)      # cod_producto del SISAGRI
    nombre = models.CharField(max_length=100, unique=True)     # nombre local: "Papa", "Alfalfa"
    grupo = models.CharField(max_length=40)                    # hortaliza, frutal, cereal_grano_andino...
    tipo = models.CharField(max_length=20)                     # transitorio / permanente / pasto
    familia = models.CharField(max_length=60, blank=True)      # familia botánica (para la rotación)
    es_leguminosa = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    ciclo_dias = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre