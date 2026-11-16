"""Puente entre la web (Django) y el motor experto de AgroPredix.

La web solo habla con este archivo; el motor no sabe nada de Django.
"""
from functools import lru_cache
from pathlib import Path

from .motor.agropredix_motor import FACTOR, cargar_modelo, explicar, influencia, recomendar


RUTA_MODELO = Path(__file__).resolve().parent / 'motor' / 'agropredix_modelo.json'


class DistritoNoCubierto(Exception):
    """El distrito de la parcela no está en el modelo (hoy: Tiabaya, Sachaca, Uchumayo)."""


@lru_cache(maxsize=1)
def modelo():
    """Carga el JSON una sola vez y lo reutiliza en cada petición."""
    return cargar_modelo(RUTA_MODELO)


def clave_distrito(distrito):
    """Distrito (modelo Django) -> clave del modelo, usando el ubigeo (más seguro que el nombre)."""
    for clave, datos in modelo()['distritos'].items():
        if int(distrito.ubigeo) == int(datos['cod_ubigeo']):
            return clave
    raise DistritoNoCubierto(distrito.nombre)


def distritos_cubiertos():
    return sorted(int(d['cod_ubigeo']) for d in modelo()['distritos'].values())


def antecesor_de(parcela):
    """Cultivo de la campaña más reciente del historial (None si no hay historial)."""
    ultimo = parcela.historial.select_related('cultivo').order_by('-campana_ini', '-fecha_registro').first()
    return ultimo.cultivo.nombre if ultimo else None


def influencia_por_factor(r, m):
    """Peso de cada factor en la idoneidad, listo para dibujar (RF-0008).

    pct = parte del efecto total (suma ~100); ayuda = True si suma, False si resta.
    """
    ctx = r['_ctx']
    inf = influencia(m, r['cod'], ctx['entradas'], ctx['omitir'])
    total = sum(abs(v) for v in inf.values()) or 1.0
    return [{'factor': k, 'etiqueta': FACTOR[k], 'puntos': round(v, 1),
             'pct': round(abs(v) / total * 100), 'ayuda': v >= 0}
            for k, v in sorted(inf.items(), key=lambda kv: -abs(kv[1]))]


def recomendar_para_parcela(parcela, mes):
    """Ranking completo para la parcela. Devuelve dict listo para la plantilla."""
    clave = clave_distrito(parcela.distrito)
    ant = antecesor_de(parcela)
    m = modelo()
    try:
        ranking = recomendar(m, clave, mes, antecesor=ant)
    except ValueError:          # antecesor no reconocido por el modelo -> se trata como desconocido
        ranking = recomendar(m, clave, mes, antecesor=None)
        ant = None
    for r in ranking:
        r['influencia'] = influencia_por_factor(r, m)
        r['explicacion'] = explicar(r, m)
        r['explicacion_detallada'] = explicar(r, m, detallado=True)
    return {'ranking': ranking, 'antecesor': ant, 'mes': int(mes), 'distrito': clave}


def nombres_distritos_cubiertos():
    return [k.title() for k in modelo()['distritos']]


def cubre(distrito):
    try:
        clave_distrito(distrito)
        return True
    except DistritoNoCubierto:
        return False