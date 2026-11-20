"""Alertas de riesgo fitosanitario por distrito (RF-0009).

Las reglas viven en `reglas_fitosanitarias.json`. Hoy son un BORRADOR: los umbrales son razonables pero genéricos
y deben validarse con un agrónomo antes de presentarlos como resultado de la tesis. Se calculan al momento a partir
del clima guardado por RF-0010, de modo que nunca quedan alertas viejas guardadas.
"""
import json
from functools import lru_cache
from pathlib import Path

from clima import servicio as clima

RUTA_REGLAS = Path(__file__).with_name('reglas_fitosanitarias.json')

BAJO, MEDIO, ALTO = 'bajo', 'medio', 'alto'
ORDEN = {ALTO: 0, MEDIO: 1, BAJO: 2}
PRESENTACION = {   # el color nunca va solo: siempre acompaña a una palabra
    BAJO: {'color': 'success', 'etiqueta': 'Riesgo bajo'},
    MEDIO: {'color': 'warning', 'etiqueta': 'Riesgo medio'},
    ALTO: {'color': 'danger', 'etiqueta': 'Riesgo alto'},
}


@lru_cache(maxsize=1)
def cargar_reglas():
    return json.loads(RUTA_REGLAS.read_text(encoding='utf-8'))


def resumen_clima(registros):
    """Promedios de la ventana: lo único que miran las reglas."""
    def media(campo):
        vals = [getattr(r, campo) for r in registros if getattr(r, campo) is not None]
        return sum(vals) / len(vals) if vals else None

    lluvias = [r.precipitacion for r in registros if r.precipitacion is not None]
    return {'humedad_media': media('humedad'), 'temp_media': media('temp_media'),
            'precip_total': sum(lluvias) if lluvias else None, 'dias': len(registros)}


def _cumple(condiciones, datos):
    for variable, limites in condiciones.items():
        valor = datos.get(variable)
        if valor is None:
            return False
        if 'min' in limites and valor < limites['min']:
            return False
        if 'max' in limites and valor > limites['max']:
            return False
    return True


def nivel_de(regla, datos):
    for nivel in (ALTO, MEDIO):
        if _cumple(regla['niveles'][nivel], datos):
            return nivel
    return BAJO


def evaluar_datos(datos, reglas=None):
    """Evalúa todas las reglas con el resumen de clima. Devuelve las alertas ordenadas de mayor a menor riesgo."""
    config = reglas or cargar_reglas()
    alertas = []
    for regla in config['reglas']:
        nivel = nivel_de(regla, datos)
        plantilla = regla['sin_riesgo'] if nivel == BAJO else regla['factor']
        alertas.append({
            'id': regla['id'], 'nombre': regla['nombre'], 'tipo': regla['tipo'], 'nivel': nivel,
            'factor': plantilla.format(**{k: (v if v is not None else 0) for k, v in datos.items()}),
            **PRESENTACION[nivel],
        })
    return sorted(alertas, key=lambda a: ORDEN[a['nivel']])


def alertas_de_distrito(distrito, hoy=None):
    """Alertas del distrito según su clima reciente, o None si no hay datos suficientes para opinar."""
    config = cargar_reglas()
    registros = clima.serie(distrito, dias=config['ventana_dias'], hoy=hoy)
    if len(registros) < config['min_dias_con_dato']:
        return None
    return evaluar_datos(resumen_clima(registros), config)


def alertas_de_usuario(usuario, hoy=None):
    """Alertas medias y altas de todas sus parcelas, las altas primero. Para el panel principal."""
    por_distrito, resultado = {}, []
    for parcela in usuario.parcelas.select_related('distrito'):
        if parcela.distrito_id not in por_distrito:
            por_distrito[parcela.distrito_id] = alertas_de_distrito(parcela.distrito, hoy)
        for a in por_distrito[parcela.distrito_id] or []:
            if a['nivel'] != BAJO:
                resultado.append({**a, 'parcela': parcela})
    return sorted(resultado, key=lambda a: (ORDEN[a['nivel']], a['parcela'].nombre))
