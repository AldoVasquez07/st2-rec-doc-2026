"""Descarga de clima diario desde NASA POWER (RF-0010).

NASA POWER es un repositorio público y gratuito que entrega temperatura, humedad relativa y precipitación
diarias para cualquier coordenada. Se eligió porque SENAMHI no ofrece una API abierta y las estaciones de los
valles de Arequipa no cubren todos los distritos. Los datos son estimaciones satelitales/de reanálisis, no
mediciones de una estación: conviene decirlo en la tesis (limitación) y, si se consigue, contrastar con SENAMHI.

Para cambiar de fuente basta con escribir otra función con la misma firma que `descargar`.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = 'https://power.larc.nasa.gov/api/temporal/daily/point'
PARAMETROS = 'T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR'
SIN_DATO = -999                  # valor que usa NASA POWER cuando no hay dato
NOMBRE = 'NASA POWER'


class FuenteNoDisponible(Exception):
    """La fuente no respondió o respondió algo que no se puede usar."""


def _valor(serie, clave):
    v = (serie or {}).get(clave)
    return None if v is None or v <= SIN_DATO else round(float(v), 2)


def descargar(latitud, longitud, inicio, fin, timeout=30):
    """Devuelve una lista de dicts, uno por día, con fecha, temp_media, temp_max, temp_min, humedad y precipitacion."""
    consulta = urllib.parse.urlencode({
        'parameters': PARAMETROS, 'community': 'AG', 'format': 'JSON',
        'latitude': latitud, 'longitude': longitud,
        'start': inicio.strftime('%Y%m%d'), 'end': fin.strftime('%Y%m%d'),
    })
    try:
        with urllib.request.urlopen(f'{URL}?{consulta}', timeout=timeout) as resp:
            cuerpo = json.load(resp)
        p = cuerpo['properties']['parameter']
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
        raise FuenteNoDisponible(f'{type(exc).__name__}: {exc}') from exc
    return normalizar(p)


def normalizar(p):
    """Pasa la respuesta de NASA POWER (un diccionario por variable) a una lista de días."""
    dias = []
    for clave in sorted(p.get('T2M', {})):
        dia = {
            'fecha': date(int(clave[:4]), int(clave[4:6]), int(clave[6:8])),
            'temp_media': _valor(p.get('T2M'), clave),
            'temp_max': _valor(p.get('T2M_MAX'), clave),
            'temp_min': _valor(p.get('T2M_MIN'), clave),
            'humedad': _valor(p.get('RH2M'), clave),
            'precipitacion': _valor(p.get('PRECTOTCORR'), clave),
        }
        if any(dia[k] is not None for k in ('temp_media', 'humedad', 'precipitacion')):
            dias.append(dia)
    return dias
