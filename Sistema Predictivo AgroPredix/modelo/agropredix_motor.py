"""
AgroPredix - Motor experto: inferencia difusa (Mamdani) + ajuste bayesiano (Beta-Binomial)

Un solo archivo; solo requiere numpy y scipy. Se usa igual en Colab, Flask o Django:

    from agropredix_motor import cargar_modelo, recomendar, explicar
    modelo = cargar_modelo('agropredix_modelo.json')
    res = recomendar(modelo, 'TIABAYA', mes=11, antecesor='Arveja Grano Verde')
    print(explicar(res[0], modelo))
"""
import json
import unicodedata
import numpy as np
from scipy.stats import beta as _beta

UNIVERSO = np.linspace(0, 100, 201)


# ------------------------------------------------------------------ funciones de pertenencia
def trapmf(x, a, b, c, d):
    """Función de pertenencia trapezoidal: 0 fuera de [a,d], 1 en [b,c]."""
    x = float(x)
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return (x - a) / (b - a) if b > a else 1.0
    return (d - x) / (d - c) if d > c else 1.0


def _serie(a, b, c, d):
    return np.array([trapmf(v, a, b, c, d) for v in UNIVERSO])


SALIDA = {'baja': _serie(0, 0, 15, 40), 'media': _serie(20, 45, 55, 80), 'alta': _serie(60, 85, 100, 100)}


def _centroide(mu):
    s = mu.sum()
    return float((UNIVERSO * mu).sum() / s) if s > 0 else 0.0


_C_BAJA, _C_ALTA = _centroide(SALIDA['baja']), _centroide(SALIDA['alta'])

# preferencia de textura expresada en % de arcilla (a, b, c, d del trapecio)
TEXTURA = {'ligero': (0, 0, 15, 28), 'medio': (6, 12, 27, 38), 'pesado': (20, 28, 45, 60), 'amplio': (0, 0, 100, 100)}


def cargar_modelo(ruta):
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


# ------------------------------------------------------------------ fuzzificación e inferencia
def fuzzificar(cultivo, e, omitir=()):
    """Convierte las entradas en grados de pertenencia. Un dato desconocido vale 0.5/0.5 (máxima incertidumbre)."""
    def par(nombre, valor, params):
        if valor is None or nombre in omitir:
            return 0.5, 0.5
        mu = trapmf(valor, *params)
        return mu, 1.0 - mu

    t = par('temperatura', e.get('temperatura'), cultivo['temp'])
    p = par('ph', e.get('ph'), cultivo['ph'])
    x = par('textura', e.get('arcilla'), TEXTURA[cultivo['textura_pref']])
    tip = min(1.0, max(0.0, ((e.get('ratio') or 0.0) - 0.15) / 0.35))
    con = 0.0 if cultivo['tolera_helada'] else min(1.0, e.get('p_helada') or 0.0)
    ant = e.get('antecesor')
    if ant is None or 'antecesor' in omitir:
        a = {'favorable': 1 / 3, 'neutro': 1 / 3, 'desfavorable': 1 / 3}
    else:
        a = {k: (1.0 if k == ant else 0.0) for k in ('favorable', 'neutro', 'desfavorable')}
    return {'temperatura': {'adecuada': t[0], 'inadecuada': t[1]},
            'ph': {'adecuado': p[0], 'inadecuado': p[1]},
            'textura': {'adecuada': x[0], 'inadecuada': x[1]},
            'antecesor': a,
            'epoca': {'tipica': tip, 'poco_usual': 1.0 - tip},
            'helada': {'con_riesgo': con, 'sin_riesgo': 1.0 - con}}


def evaluar_reglas(reglas, grados):
    """Mamdani: fuerza = mínimo de las condiciones (OR dentro de una variable = máximo);
    agregación por máximo; defuzzificación por centroide. Devuelve (índice 0-100, reglas activadas)."""
    agregado = np.zeros_like(UNIVERSO)
    activadas = []
    for r in reglas:
        fuerza = 1.0
        for var, terminos in r['si'].items():
            fuerza = min(fuerza, max(grados[var][t] for t in terminos))
        if fuerza > 0:
            agregado = np.maximum(agregado, np.minimum(fuerza, SALIDA[r['entonces']]))
            activadas.append({'id': r['id'], 'fuerza': round(float(fuerza), 3), 'nivel': r['entonces'], 'texto': r['texto']})
    if agregado.sum() == 0:
        return 0.0, activadas
    s = (_centroide(agregado) - _C_BAJA) / (_C_ALTA - _C_BAJA) * 100.0
    return float(min(100.0, max(0.0, s))), activadas


def idoneidad(modelo, cod, entradas, omitir=()):
    g = fuzzificar(modelo['cultivos'][cod], entradas, omitir)
    s, act = evaluar_reglas(modelo['reglas'], g)
    return s, act, g


def influencia(modelo, cod, entradas, omitir=()):
    """Cuánto aporta cada factor: índice con el factor menos el índice sin él (positivo = ayuda, negativo = perjudica)."""
    base, _, _ = idoneidad(modelo, cod, entradas, omitir)
    out = {}
    for v in ('temperatura', 'ph', 'textura', 'antecesor'):
        if v in omitir or (v == 'antecesor' and entradas.get('antecesor') is None):
            continue
        s, _, _ = idoneidad(modelo, cod, entradas, tuple(omitir) + (v,))
        out[v] = base - s
    return out


# ------------------------------------------------------------------ ajuste bayesiano (Beta-Binomial)
def certeza_bayes(modelo, distrito, cod, n_faltantes=0):
    cfg = modelo['config']
    p0 = modelo['prior_regional'].get(cod, 0.5)
    a0, b0 = cfg['k_prior'] * p0, cfg['k_prior'] * (1 - p0)
    h = modelo['historial'].get(distrito, {}).get(cod, {'exitos': 0, 'n': 0})
    a, b = a0 + h['exitos'], b0 + (h['n'] - h['exitos'])
    media = a / (a + b)
    lo, hi = _beta.ppf([0.025, 0.975], a, b)
    factor = max(cfg['min_factor'], 1.0 - cfg['penalizacion_faltante'] * n_faltantes)
    return {'p_exito': float(media), 'ic95': (float(lo), float(hi)), 'n_hist': h['n'], 'exitos': h['exitos'],
            'factor_datos': factor, 'certeza_pct': float(100 * media * factor)}


# ------------------------------------------------------------------ rotación y recomendación
def _norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s).lower()) if unicodedata.category(c) != 'Mn').strip()


def nivel_rotacion(modelo, antecesor, cultivo):
    if antecesor is None:
        return None
    rot = modelo['rotacion']
    if antecesor in rot and cultivo in rot[antecesor]:
        return rot[antecesor][cultivo]
    fa, fc = modelo['familias'].get(antecesor), modelo['familias'].get(cultivo)
    if fa and fa == fc:
        return 'desfavorable'
    return 'favorable' if fa == 'Fabaceae' else 'neutro'


def _resolver_nombre(modelo, texto):
    if texto is None:
        return None
    n = _norm(texto)
    for nombre in set(modelo['familias']) | {c['nombre'] for c in modelo['cultivos'].values()}:
        if _norm(nombre) == n:
            return nombre
    for nombre in modelo['familias']:
        if _norm(nombre).startswith(n):
            return nombre
    raise ValueError(f'Antecesor no reconocido: {texto}')


def recomendar(modelo, distrito, mes, antecesor=None, ph=None, arcilla=None, temp_media=None, omitir=()):
    """Ranking de cultivos para un distrito y un mes. ph/arcilla/temp_media reemplazan a las estimaciones
    (p. ej. un análisis de laboratorio). 'omitir' fuerza a tratar un dato como desconocido."""
    distrito = distrito.upper()
    d = modelo['distritos'][distrito]
    cm = d['clima'][str(int(mes))]
    ent = {'ph': ph if ph is not None else d['ph'],
           'arcilla': arcilla if arcilla is not None else d['arcilla'],
           'temperatura': temp_media if temp_media is not None else cm['temp_media'],
           'p_helada': cm['p_helada']}
    ant = _resolver_nombre(modelo, antecesor)
    faltantes = set(omitir)
    if ant is None:
        faltantes.add('antecesor')
    for var, val in (('ph', ent['ph']), ('textura', ent['arcilla']), ('temperatura', ent['temperatura'])):
        if val is None:
            faltantes.add(var)
    omitir_f = tuple(sorted(faltantes - {'antecesor'})) + (('antecesor',) if 'antecesor' in faltantes else ())
    res = []
    for cod, c in modelo['cultivos'].items():
        e = dict(ent)
        e['ratio'] = modelo['calendario'].get(distrito, {}).get(cod, {}).get(str(int(mes)), 0.0)
        e['antecesor'] = nivel_rotacion(modelo, ant, c['nombre'])
        idon, act, g = idoneidad(modelo, cod, e, omitir_f)
        bay = certeza_bayes(modelo, distrito, cod, len(faltantes))
        res.append({'cod': cod, 'cultivo': c['nombre'], 'idoneidad': round(idon, 1),
                    'certeza_pct': round(bay['certeza_pct'], 1),
                    'idoneidad_ajustada': round(idon * bay['certeza_pct'] / 100, 1),
                    'nivel': 'Alta' if idon >= 66 else ('Media' if idon >= 33 else 'Baja'),
                    'bayes': bay, 'reglas': act, 'grados': g,
                    '_ctx': {'entradas': e, 'omitir': omitir_f, 'distrito': distrito, 'mes': int(mes),
                             'antecesor': ant, 'rotacion': e['antecesor']}})
    res.sort(key=lambda r: (r['idoneidad_ajustada'], r['idoneidad']), reverse=True)
    for i, r in enumerate(res, 1):
        r['puesto'] = i
    return res


# ------------------------------------------------------------------ explicación (RF-0008)
def _palabra(mu):
    return 'muy adecuado' if mu >= 0.8 else 'adecuado' if mu >= 0.5 else 'regular' if mu >= 0.2 else 'poco adecuado'


MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre']
FACTOR = {'temperatura': 'La temperatura del mes', 'ph': 'La acidez del suelo', 'textura': 'El tipo de suelo',
          'antecesor': 'El cultivo anterior'}


def explicar(r, modelo, detallado=False):
    """Texto en lenguaje sencillo. Vista resumida por defecto; detallado=True agrega reglas e influencia."""
    ctx, g, b = r['_ctx'], r['grados'], r['bayes']
    ant = ctx['antecesor']
    rot = {'favorable': 'ayuda al siguiente cultivo', 'neutro': 'no ayuda ni perjudica', 'desfavorable': 'no conviene repetir esa familia',
           None: 'no se registró'}[ctx['rotacion']]
    lineas = [f"{r['puesto']}. {r['cultivo']}: idoneidad {r['idoneidad']:.0f}/100 ({r['nivel']}), certeza {r['certeza_pct']:.0f}%",
              f"   • Clima de {MESES[ctx['mes'] - 1]}: {_palabra(g['temperatura']['adecuada'])}. "
              f"Acidez del suelo: {_palabra(g['ph']['adecuado'])}. Tipo de suelo: {_palabra(g['textura']['adecuada'])}.",
              f"   • Cultivo anterior ({ant or 'sin registrar'}): {rot}.",
              f"   • Época: {'habitual' if g['epoca']['tipica'] >= 0.5 else 'poco habitual'} para sembrarlo en {ctx['distrito'].title()}.",
              f"   • Historial: en {b['n_hist']} campañas con datos en la zona, {b['exitos']} tuvieron buen rendimiento."]
    if b['factor_datos'] < 1:
        lineas.append('   • La certeza es menor porque faltan datos de entrada.')
    if detallado:
        inf = influencia(modelo, r['cod'], ctx['entradas'], ctx['omitir'])
        tot = sum(abs(v) for v in inf.values()) or 1.0
        lineas.append('   Influencia de cada factor:')
        for k, v in sorted(inf.items(), key=lambda kv: -abs(kv[1])):
            lineas.append(f"     - {FACTOR[k]}: {abs(v) / tot * 100:.0f}% ({'ayuda' if v >= 0 else 'perjudica'})")
        lineas.append('   Reglas que se activaron:')
        for a in sorted(r['reglas'], key=lambda x: -x['fuerza']):
            lineas.append(f"     - [{a['id']}] fuerza {a['fuerza']:.2f} → {a['nivel']}: {a['texto']}")
    return '\n'.join(lineas)
