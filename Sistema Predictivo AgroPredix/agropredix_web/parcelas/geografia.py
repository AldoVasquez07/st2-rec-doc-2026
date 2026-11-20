"""Ubicación de una parcela a partir de sus coordenadas (RF-0004)."""
from math import asin, cos, radians, sin, sqrt

from .models import Distrito

MAX_KM = 25     # más lejos que esto, no se adivina el distrito


def km_entre(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(radians, (lat1, lon1, lat2, lon2))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def distrito_mas_cercano(latitud, longitud, max_km=MAX_KM):
    """Distrito cuyo punto de referencia queda más cerca de la coordenada (None si ninguno está a max_km o menos).

    Es una aproximación: usa el punto central de cada distrito, no sus límites. Con los límites oficiales
    (GeoJSON del INEI/IGN) se podría hacer exacto; hasta entonces el agricultor puede corregirlo en la lista.
    """
    mejor, mejor_km = None, None
    for d in Distrito.objects.exclude(latitud__isnull=True).exclude(longitud__isnull=True):
        km = km_entre(latitud, longitud, d.latitud, d.longitud)
        if mejor_km is None or km < mejor_km:
            mejor, mejor_km = d, km
    return mejor if mejor is not None and mejor_km <= max_km else None