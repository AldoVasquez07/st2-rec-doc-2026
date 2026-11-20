from django.conf import settings
from django.db import models
from django.utils import timezone

from parcelas.models import Parcela
from recomendaciones.models import Recomendacion


class SolicitudAsistencia(models.Model):
    """Duda del agricultor derivada a un especialista (RF-0014)."""
    class Estado(models.TextChoices):
        ENVIADA = 'enviada', 'Enviada'
        EN_REVISION = 'en_revision', 'En revisión'
        RESPONDIDA = 'respondida', 'Respondida'

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='solicitudes')
    parcela = models.ForeignKey(Parcela, null=True, blank=True, on_delete=models.SET_NULL, related_name='solicitudes')
    recomendacion = models.ForeignKey(Recomendacion, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='solicitudes')       # la recomendación que adjunta
    descripcion = models.TextField(max_length=1000)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ENVIADA)
    respuesta = models.TextField(blank=True)                            # en lenguaje simple
    respondida_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='respuestas_dadas')
    creada = models.DateTimeField(auto_now_add=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creada']
        verbose_name = 'solicitud de asistencia'
        verbose_name_plural = 'solicitudes de asistencia'

    def save(self, *args, **kwargs):
        # Escribir la respuesta la marca como respondida; el especialista no tiene que acordarse de cambiar el estado.
        if self.respuesta.strip() and self.estado != self.Estado.RESPONDIDA:
            self.estado = self.Estado.RESPONDIDA
        if self.estado == self.Estado.RESPONDIDA and self.fecha_respuesta is None:
            self.fecha_respuesta = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.usuario.nombre}: {self.descripcion[:40]} ({self.get_estado_display()})'
