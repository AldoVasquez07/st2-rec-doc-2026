"""Generación y envío de recordatorios de campaña (RF-0013)."""
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from recomendaciones.models import Siembra

from .models import PreferenciaRecordatorio, Recordatorio


def preferencias_de(usuario):
    return PreferenciaRecordatorio.objects.get_or_create(usuario=usuario)[0]


def generar(hoy=None):
    """Crea los recordatorios que ya tocan, a partir de las fechas estimadas de cada siembra."""
    hoy = hoy or timezone.localdate()
    nuevos = []
    siembras = Siembra.objects.filter(resultado='').select_related('recomendacion__parcela__usuario')
    for s in siembras:
        usuario, parcela = s.parcela.usuario, s.parcela
        pref = preferencias_de(usuario)
        eventos = []
        if pref.avisar_siembra:
            eventos.append(('siembra', s.fecha_siembra,
                            f'Se acerca la siembra de {s.cultivo} en «{parcela.nombre}» ({s.fecha_siembra:%d/%m/%Y}).'))
        if pref.avisar_cosecha:
            eventos.append(('cosecha', s.cierre_estimado,
                            f'Se acerca la cosecha de {s.cultivo} en «{parcela.nombre}» ({s.cierre_estimado:%d/%m/%Y}).'))
        for tipo, fecha, texto in eventos:
            if fecha < hoy or fecha - timedelta(days=pref.dias_antes) > hoy:
                continue                       # ya pasó, o todavía falta para avisar
            r, creado = Recordatorio.objects.get_or_create(
                siembra=s, tipo=tipo, defaults={'usuario': usuario, 'fecha_evento': fecha, 'mensaje': texto})
            if creado:
                nuevos.append(r)
    return nuevos


def _push(r):
    if not settings.VAPID_PRIVATE_KEY:
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False
    enviados = 0
    for sub in r.usuario.suscripciones_push.all():
        try:
            webpush(subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                    data=json.dumps({'titulo': 'AgroPredix', 'texto': r.mensaje, 'url': '/recordatorios/'}),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={'sub': settings.VAPID_CONTACTO})
            enviados += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404, 410):
                sub.delete()                   # el celular ya no recibe: se borra la suscripción
    return enviados > 0


def _sms(r):
    """PENDIENTE: conectar aquí el proveedor de SMS que elijas (Twilio, etc.)."""
    return False


def enviar(r):
    canal = preferencias_de(r.usuario).canal
    if canal == 'push':
        ok = _push(r)
    elif canal == 'sms':
        ok = _sms(r) if settings.SMS_HABILITADO else False
    else:
        ok = True                              # "app": ya es visible en el panel
    if ok:
        r.enviado = timezone.now()
        r.save(update_fields=['enviado'])
    return ok


def enviar_pendientes(hoy=None):
    hoy = hoy or timezone.localdate()
    pendientes = Recordatorio.objects.filter(enviado__isnull=True, fecha_evento__gte=hoy).select_related('usuario')
    return sum(1 for r in pendientes if enviar(r))