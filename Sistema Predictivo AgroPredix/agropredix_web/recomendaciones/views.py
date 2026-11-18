from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from parcelas.models import Parcela

from . import servicio
from .models import Recomendacion

MESES = [(i, n.capitalize()) for i, n in enumerate(
    ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
     'setiembre', 'octubre', 'noviembre', 'diciembre'], 1)]

CAMPOS_GUARDADOS = ('puesto', 'cultivo', 'idoneidad', 'certeza_pct', 'idoneidad_ajustada',
                    'nivel', 'influencia', 'explicacion', 'explicacion_detallada')


def _mes_valido(texto):
    try:
        mes = int(texto)
    except (TypeError, ValueError):
        return date.today().month
    return mes if 1 <= mes <= 12 else date.today().month


@login_required
def generar(request, pk):
    parcela = get_object_or_404(Parcela.objects.select_related('distrito'), pk=pk, usuario=request.user)
    cubierto = servicio.cubre(parcela.distrito)

    if request.method == 'POST' and cubierto:
        mes = _mes_valido(request.POST.get('mes'))
        datos = servicio.recomendar_para_parcela(parcela, mes)
        rec = Recomendacion.objects.create(
            parcela=parcela, mes=mes, antecesor=datos['antecesor'] or '', suelo=datos['suelo'],
            resultado=[{k: r[k] for k in CAMPOS_GUARDADOS} for r in datos['ranking']])
        return redirect('recomendaciones:detalle', rpk=rec.pk)

    return render(request, 'recomendaciones/generar.html', {
        'parcela': parcela, 'cubierto': cubierto, 'meses': MESES,
        'mes_actual': date.today().month, 'suelo': servicio.analisis_vigente(parcela),
        'distritos_cubiertos': servicio.nombres_distritos_cubiertos(),
        'anteriores': parcela.recomendaciones.all()[:5]})


@login_required
def lista(request):
    """Últimas recomendaciones del agricultor (las que quedan disponibles sin conexión)."""
    recomendaciones = list(Recomendacion.objects.filter(parcela__usuario=request.user)
                           .select_related('parcela__distrito')[:20])
    for r in recomendaciones:
        r.mes_nombre = MESES[r.mes - 1][1]
        r.mejor = r.resultado[0] if r.resultado else None
    return render(request, 'recomendaciones/lista.html', {'recomendaciones': recomendaciones})


@login_required
def detalle(request, rpk):
    rec = get_object_or_404(Recomendacion.objects.select_related('parcela__distrito'),
                            pk=rpk, parcela__usuario=request.user)   # de otro usuario: 404
    return render(request, 'recomendaciones/detalle.html', {
        'rec': rec, 'parcela': rec.parcela, 'mes_nombre': MESES[rec.mes - 1][1],
        'ranking': rec.resultado})
    