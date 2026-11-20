from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from recomendaciones.models import Siembra


class PreferenciaRecordatorio(models.Model):
    """Qué avisos quiere el agricultor y por qué canal (RF-0013)."""
    class Canal(models.TextChoices):
        APP = 'app', 'Solo dentro de la app'
        PUSH = 'push', 'Notificación en el celular (push)'
        SMS = 'sms', 'Mensaje de texto (SMS)'

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='pref_recordatorios')
    canal = models.CharField('¿Cómo quiere recibir los avisos?', max_length=4,
                             choices=Canal.choices, default=Canal.APP)
    avisar_siembra = models.BooleanField('Avisarme de la fecha de siembra', default=True)
    avisar_cosecha = models.BooleanField('Avisarme de la fecha de cosecha', default=True)
    dias_antes = models.PositiveSmallIntegerField('Días de anticipación', default=3,
                                                  validators=[MaxValueValidator(30)])


class SuscripcionPush(models.Model):
    """Un celular o navegador que aceptó recibir notificaciones push."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='suscripciones_push')
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    creada = models.DateTimeField(auto_now_add=True)


class Recordatorio(models.Model):
    class Tipo(models.TextChoices):
        SIEMBRA = 'siembra', 'Siembra'
        COSECHA = 'cosecha', 'Cosecha'

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recordatorios')
    siembra = models.ForeignKey(Siembra, on_delete=models.CASCADE, related_name='recordatorios')
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    fecha_evento = models.DateField()
    mensaje = models.CharField(max_length=250)
    creado = models.DateTimeField(auto_now_add=True)
    enviado = models.DateTimeField(null=True, blank=True)     # cuándo salió por el canal elegido
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ['-creado']
        constraints = [models.UniqueConstraint(fields=['siembra', 'tipo'], name='un_recordatorio_por_tipo')]