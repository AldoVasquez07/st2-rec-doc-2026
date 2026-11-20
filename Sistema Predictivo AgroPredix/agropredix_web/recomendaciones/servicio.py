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

def analisis_vigente(parcela):
    """Análisis de suelo más reciente de la parcela (None si no cargó ninguno)."""
    return parcela.analisis.first()

# Qué % de arcilla se supone según cómo describe su tierra el agricultor (RF-0004).
# Valores de partida: los debe validar el agrónomo del panel de expertos.
ARCILLA_POR_TIERRA = {'suelta': 10.0, 'media': 20.0, 'pesada': 40.0}

def _resumen_suelo(ranking, suelo, arcilla_declarada=False):
    """Qué valores de suelo se usaron y de dónde vienen: análisis, lo que indicó el agricultor o la zona."""
    ent = ranking[0]['_ctx']['entradas']

    def dato(clave, medido):
        v = ent.get(clave)
        return {'valor': None if v is None else round(float(v), 1), 'medido': medido}

    arcilla_medida = bool(suelo and suelo.arcilla is not None)
    return {'ph': dato('ph', bool(suelo and suelo.ph is not None)),
            'arcilla': {**dato('arcilla', arcilla_medida), 'declarada': arcilla_declarada and not arcilla_medida},
            'fecha': f'{suelo.fecha:%d/%m/%Y}' if suelo else ''}


def recomendar_para_parcela(parcela, mes, tierra=None, ultimo_cultivo=None):
    """Ranking completo para la parcela. Devuelve dict listo para la plantilla.

    `tierra` ('suelta', 'media' o 'pesada') y `ultimo_cultivo` (nombre) son respuestas opcionales del agricultor.
    Orden de prioridad: análisis de laboratorio > respuesta del agricultor > estimación de la zona.
    """
    clave = clave_distrito(parcela.distrito)
    ant = antecesor_de(parcela) or ultimo_cultivo     # el historial registrado manda sobre lo que responda
    suelo = analisis_vigente(parcela)
    # Lo que falte en el análisis (pH o arcilla) lo completa el motor con la estimación de la zona
    laboratorio = {'ph': suelo.ph, 'arcilla': suelo.arcilla} if suelo else {}
    declarada = ARCILLA_POR_TIERRA.get(tierra)
    if declarada is not None and laboratorio.get('arcilla') is None:
        laboratorio['arcilla'] = declarada
    m = modelo()
    try:
        ranking = recomendar(m, clave, mes, antecesor=ant, **laboratorio)
    except ValueError:          # antecesor no reconocido por el modelo -> se trata como desconocido
        ranking = recomendar(m, clave, mes, antecesor=None, **laboratorio)
        ant = None
    for r in ranking:
        r['influencia'] = influencia_por_factor(r, m)
        r['explicacion'] = explicar(r, m)
        r['explicacion_detallada'] = explicar(r, m, detallado=True)
    return {'ranking': ranking, 'antecesor': ant, 'mes': int(mes), 'distrito': clave,
            'suelo': _resumen_suelo(ranking, suelo, arcilla_declarada=declarada is not None)}


def nombres_distritos_cubiertos():
    return [k.title() for k in modelo()['distritos']]


def cubre(distrito):
    try:
        clave_distrito(distrito)
        return True
    except DistritoNoCubierto:
        return False