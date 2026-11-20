"""Reportes agregados y anónimos por distrito (RF-0012)."""
from collections import Counter
from math import asin, cos, radians, sin, sqrt

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from parcelas.models import Distrito, Parcela
from recomendaciones.models import Recomendacion, Siembra

TOP = 5
MAX_VECINOS = 4
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def minimo_usuarios():
    return getattr(settings, 'REPORTES_MIN_USUARIOS', 5)


def _km(a, b):
    la1, lo1, la2, lo2 = map(radians, (a.latitud, a.longitud, b.latitud, b.longitud))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def vecinos(distrito):
    """Los distritos más cercanos de la misma provincia que tienen parcelas registradas."""
    if distrito.latitud is None or distrito.longitud is None:
        return []
    otros = (Distrito.objects.filter(provincia=distrito.provincia, parcelas__isnull=False,
                                     latitud__isnull=False, longitud__isnull=False)
             .exclude(pk=distrito.pk).distinct())
    return sorted(otros, key=lambda d: _km(distrito, d))[:MAX_VECINOS]


def usuarios_por_distrito():
    filas = Parcela.objects.order_by().values('distrito').annotate(n=Count('usuario', distinct=True))
    return {f['distrito']: f['n'] for f in filas}


def ultimos_meses(hoy, n=12):
    anio, mes, lista = hoy.year, hoy.month, []
    for _ in range(n):
        lista.append((anio, mes))
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return lista[::-1]


def _reporte(distrito, usuarios, meses):
    if usuarios < minimo_usuarios():          # sin suficientes usuarios no se muestra ningún dato
        return {'distrito': distrito, 'visible': False}
    recomendados = Counter()
    for resultado in Recomendacion.objects.filter(parcela__distrito=distrito).values_list('resultado', flat=True):
        primero = next((r for r in resultado if r.get('puesto') == 1), None)
        if primero:
            recomendados[primero['cultivo']] += 1
    sembrados, por_mes = Counter(), Counter()
    filas = Siembra.objects.filter(recomendacion__parcela__distrito=distrito).values_list('cultivo', 'fecha_siembra')
    for cultivo, fecha in filas:
        sembrados[cultivo] += 1
        por_mes[(fecha.year, fecha.month)] += 1
    return {'distrito': distrito, 'visible': True,
            'recomendados': dict(recomendados.most_common(TOP)),
            'sembrados': dict(sembrados.most_common(TOP)),
            'por_mes': [por_mes.get(m, 0) for m in meses]}


def _alinear(reportes, clave):
    """Mismas etiquetas (cultivos) para todos los distritos, así las barras se pueden comparar."""
    etiquetas = []
    for r in reportes:
        for cultivo in r[clave]:
            if cultivo not in etiquetas:
                etiquetas.append(cultivo)
    return {'etiquetas': etiquetas,
            'series': [{'nombre': r['distrito'].nombre, 'valores': [r[clave].get(c, 0) for c in etiquetas]}
                       for r in reportes]}


def reporte_zona(distrito, hoy=None):
    meses = ultimos_meses(hoy or timezone.localdate())
    usuarios = usuarios_por_distrito()
    zonas = [distrito] + vecinos(distrito)
    reportes = [_reporte(z, usuarios.get(z.pk, 0), meses) for z in zonas]
    visibles = [r for r in reportes if r['visible']]
    return {
        'reportes': reportes, 'minimo': minimo_usuarios(), 'hay_datos': bool(visibles),
        'graficos': {
            'recomendados': _alinear(visibles, 'recomendados'),
            'sembrados': _alinear(visibles, 'sembrados'),
            'meses': [f'{MESES[m - 1]} {a}' for a, m in meses],
            'por_mes': [{'nombre': r['distrito'].nombre, 'valores': r['por_mes']} for r in visibles],
        },
    }