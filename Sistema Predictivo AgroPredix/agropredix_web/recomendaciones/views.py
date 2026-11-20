from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from parcelas.models import Parcela

from . import seguimiento, servicio
from .forms import PreguntasForm, SiembraForm, ValoracionForm
from .models import Recomendacion, Siembra



MESES = [(i, n.capitalize()) for i, n in enumerate(
    ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
     'setiembre', 'octubre', 'noviembre', 'diciembre'], 1)]


CAMPOS_GUARDADOS = ('puesto', 'cod', 'cultivo', 'idoneidad', 'certeza_pct', 'idoneidad_ajustada',
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

    preguntar_cultivo = servicio.antecesor_de(parcela) is None
    preguntas = PreguntasForm(request.POST or None, preguntar_cultivo=preguntar_cultivo)

    if request.method == 'POST' and cubierto and preguntas.is_valid():
        mes = _mes_valido(request.POST.get('mes'))
        ultimo = preguntas.cleaned_data.get('ultimo_cultivo')
        datos = servicio.recomendar_para_parcela(
            parcela, mes, tierra=preguntas.cleaned_data.get('tierra') or None,
            ultimo_cultivo=ultimo.nombre if ultimo else None)
        rec = Recomendacion.objects.create(
            parcela=parcela, mes=mes, antecesor=datos['antecesor'] or '', suelo=datos['suelo'],
            resultado=[{k: r[k] for k in CAMPOS_GUARDADOS} for r in datos['ranking']])
        return redirect('recomendaciones:detalle', rpk=rec.pk)

    return render(request, 'recomendaciones/generar.html', {
        'parcela': parcela, 'cubierto': cubierto, 'meses': MESES, 'preguntas': preguntas, 
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
    siembras = {s.cultivo_cod: s for s in rec.siembras.all()}
    ranking = rec.resultado
    for r in ranking:                                    # marca los cultivos que el agricultor ya decidió sembrar
        r['siembra'] = siembras.get(r.get('cod'))
    return render(request, 'recomendaciones/detalle.html', {
        'rec': rec, 'parcela': rec.parcela, 'mes_nombre': MESES[rec.mes - 1][1],
        'ranking': ranking})
    

# ---------- SEGUIMIENTO Y RETROALIMENTACIÓN POST-CAMPAÑA (RF-0011) ----------
@login_required
@require_http_methods(['GET', 'POST'])
def sembrar(request, rpk, cod):
    """El agricultor indica que va a sembrar uno de los cultivos recomendados."""
    rec = get_object_or_404(Recomendacion.objects.select_related('parcela'), pk=rpk, parcela__usuario=request.user)
    elegido = next((r for r in rec.resultado if r.get('cod') == cod), None)
    if elegido is None:
        raise Http404('Ese cultivo no está en esta recomendación.')
    existente = rec.siembras.filter(cultivo_cod=cod).first()
    if existente:
        messages.info(request, f'Ya registró la siembra de {existente.cultivo}.')
        return redirect('recomendaciones:seguimiento')

    form = SiembraForm(request.POST or None, initial={'fecha_siembra': seguimiento.siembra_sugerida(rec)})
    if request.method == 'POST' and form.is_valid():
        fecha = form.cleaned_data['fecha_siembra']
        cierre = form.cleaned_data['cierre_estimado'] or seguimiento.cierre_por_defecto(cod, fecha)
        Siembra.objects.create(
            recomendacion=rec, cultivo_cod=cod, cultivo=elegido['cultivo'], puesto=elegido['puesto'],
            idoneidad=elegido['idoneidad'], certeza_pct=elegido['certeza_pct'],
            fecha_siembra=fecha, cierre_estimado=cierre)
        messages.success(request, f'Anotado. Le preguntaremos cómo le fue con {elegido["cultivo"]} '
                                  f'hacia el {cierre:%d/%m/%Y}.')
        return redirect('recomendaciones:seguimiento')
    return render(request, 'recomendaciones/sembrar.html', {
        'rec': rec, 'parcela': rec.parcela, 'cultivo': elegido['cultivo'], 'form': form,
        'ciclo': seguimiento.ciclo_dias(cod)})


@login_required
def seguimiento_lista(request):
    hoy = timezone.localdate()
    siembras = (Siembra.objects.filter(recomendacion__parcela__usuario=request.user)
                .select_related('recomendacion__parcela'))
    return render(request, 'recomendaciones/seguimiento.html', {
        'pendientes': [s for s in siembras if not s.valorada and s.cierre_estimado <= hoy],
        'en_curso': [s for s in siembras if not s.valorada and s.cierre_estimado > hoy],
        'valoradas': sorted((s for s in siembras if s.valorada), key=lambda s: s.fecha_valoracion, reverse=True)})


@login_required
@require_http_methods(['GET', 'POST'])
def valorar(request, spk):
    siembra = get_object_or_404(Siembra.objects.select_related('recomendacion__parcela'),
                                pk=spk, recomendacion__parcela__usuario=request.user)
    if siembra.valorada:
        messages.info(request, 'Ya registró su valoración de esta siembra. ¡Gracias!')
        return redirect('recomendaciones:seguimiento')
    form = ValoracionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        siembra.resultado = form.cleaned_data['resultado']
        siembra.comentario = form.cleaned_data['comentario'].strip()
        siembra.fecha_valoracion = timezone.now()
        siembra.save()
        if seguimiento.registrar_en_historial(siembra):
            messages.success(request, 'Gracias por contarnos. También quedó anotado en el historial de su parcela.')
        else:
            messages.success(request, 'Gracias por contarnos cómo le fue.')
        return redirect('recomendaciones:seguimiento')
    return render(request, 'recomendaciones/valorar.html', {'siembra': siembra, 'form': form})
    