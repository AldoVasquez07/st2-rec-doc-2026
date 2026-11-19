"""Seguimiento de siembras y retroalimentación post-campaña (RF-0011)."""
from datetime import date, timedelta

from cultivos.models import Cultivo
from parcelas.models import HistorialCampana

from .models import Siembra

CICLO_POR_DEFECTO = 120      # días, si el cultivo no tiene su ciclo cargado


def ciclo_dias(cultivo_cod):
    """Días típicos de siembra a cosecha del cultivo (o el valor por defecto)."""
    dias = Cultivo.objects.filter(codigo=cultivo_cod).values_list('ciclo_dias', flat=True).first()
    return dias or CICLO_POR_DEFECTO


def cierre_por_defecto(cultivo_cod, fecha_siembra):
    return fecha_siembra + timedelta(days=ciclo_dias(cultivo_cod))


def siembra_sugerida(recomendacion):
    """Fecha de siembra que se propone: el mes por el que el agricultor consultó."""
    consulta = recomendacion.fecha.date()
    if recomendacion.mes == consulta.month:
        return consulta
    anio = consulta.year if recomendacion.mes > consulta.month else consulta.year + 1
    return date(anio, recomendacion.mes, 1)


def pendientes_de_valorar(usuario, hoy=None):
    """Siembras cuyo cierre estimado ya llegó y aún no fueron valoradas."""
    return (Siembra.objects
            .filter(recomendacion__parcela__usuario=usuario, resultado='', cierre_estimado__lte=hoy or date.today())
            .select_related('recomendacion__parcela'))


def campana_de(fecha):
    """Año en que empieza la campaña agrícola de esa fecha (la campaña empieza en agosto)."""
    return fecha.year if fecha.month >= 8 else fecha.year - 1


def registrar_en_historial(siembra):
    """Copia la valoración al historial de la parcela, para que cuente como cultivo antecesor.

    Devuelve True si quedó registrada. Si el cultivo no está en el catálogo no se registra.
    """
    cultivo = Cultivo.objects.filter(codigo=siembra.cultivo_cod).first()
    if cultivo is None or not siembra.resultado:
        return False
    HistorialCampana.objects.update_or_create(
        parcela=siembra.parcela, cultivo=cultivo, campana_ini=campana_de(siembra.fecha_siembra),
        defaults={'resultado': siembra.resultado})
    return True