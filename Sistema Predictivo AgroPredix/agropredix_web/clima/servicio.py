"""Actualización y consulta del clima por distrito (RF-0010)."""
from datetime import date, timedelta

from parcelas.models import Distrito

from . import fuentes
from .models import ActualizacionClima, RegistroClima

DIAS_POR_DEFECTO = 60         # ventana que se descarga la primera vez
DIAS_DE_REVISION = 7          # se vuelve a pedir lo último guardado: la fuente corrige datos recientes
DIAS_MAX_ATRASO = 7           # si el último dato es más viejo que esto, se avisa que está desactualizado
RETRASO_FUENTE = 2            # NASA POWER publica con ~2 días de retraso: no se pide "hoy"


def distritos_con_parcelas():
    return Distrito.objects.filter(parcelas__isnull=False).distinct()


def actualizar_distrito(distrito, dias=DIAS_POR_DEFECTO, descargar=None, hoy=None):
    """Descarga y guarda el clima reciente. Nunca lanza error: si la fuente falla, lo anota y conserva lo guardado.

    Devuelve la cantidad de días guardados, o None si la descarga falló.
    """
    descargar = descargar or fuentes.descargar
    hoy = hoy or date.today()
    if distrito.latitud is None or distrito.longitud is None:
        ActualizacionClima.objects.create(distrito=distrito, exito=False, mensaje='El distrito no tiene coordenadas.')
        return None

    fin = hoy - timedelta(days=RETRASO_FUENTE)
    ultimo = RegistroClima.objects.filter(distrito=distrito).order_by('-fecha').values_list('fecha', flat=True).first()
    inicio = (ultimo - timedelta(days=DIAS_DE_REVISION)) if ultimo else fin - timedelta(days=dias)
    inicio = max(inicio, fin - timedelta(days=365))
    try:
        registros = descargar(distrito.latitud, distrito.longitud, inicio, fin)
    except fuentes.FuenteNoDisponible as exc:
        ActualizacionClima.objects.create(distrito=distrito, exito=False, mensaje=str(exc)[:300])
        return None

    for r in registros:
        RegistroClima.objects.update_or_create(
            distrito=distrito, fecha=r['fecha'],
            defaults={k: r[k] for k in ('temp_media', 'temp_max', 'temp_min', 'humedad', 'precipitacion')}
            | {'fuente': fuentes.NOMBRE})
    ActualizacionClima.objects.create(distrito=distrito, exito=True, registros=len(registros))
    return len(registros)


def serie(distrito, dias=30, hoy=None):
    """Registros de los últimos `dias` días contados desde el último dato guardado (no desde hoy)."""
    ultimo = (RegistroClima.objects.filter(distrito=distrito).order_by('-fecha')
              .values_list('fecha', flat=True).first())
    if ultimo is None:
        return []
    return list(RegistroClima.objects.filter(distrito=distrito, fecha__gt=ultimo - timedelta(days=dias)))


def estado(distrito, hoy=None):
    """Qué tan al día están los datos, para avisarle al agricultor con claridad (criterio de RF-0010)."""
    hoy = hoy or date.today()
    ultimo_dato = (RegistroClima.objects.filter(distrito=distrito).order_by('-fecha')
                   .values_list('fecha', flat=True).first())
    intento = ActualizacionClima.objects.filter(distrito=distrito).first()          # el más reciente
    ok = ActualizacionClima.objects.filter(distrito=distrito, exito=True).first()
    ultimo_fallo = intento is not None and not intento.exito
    atrasado = ultimo_dato is not None and (hoy - ultimo_dato).days > DIAS_MAX_ATRASO
    return {
        'hay_datos': ultimo_dato is not None,
        'ultimo_dato': ultimo_dato,
        'ultima_actualizacion': ok.fecha if ok else None,
        'fuente_fallo': ultimo_fallo,
        'desactualizado': ultimo_fallo or atrasado,
    }
