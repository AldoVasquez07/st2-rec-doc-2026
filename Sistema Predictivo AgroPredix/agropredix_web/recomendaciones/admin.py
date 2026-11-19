from django.contrib import admin

from .models import Recomendacion, Siembra

@admin.register(Recomendacion)
class RecomendacionAdmin(admin.ModelAdmin):
    list_display = ('parcela', 'mes', 'antecesor', 'fecha')
    list_filter = ('mes',)
    
@admin.register(Siembra)
class SiembraAdmin(admin.ModelAdmin):
    """Retroalimentación de los agricultores: insumo para ajustar las reglas del motor."""
    list_display = ('cultivo', 'parcela', 'fecha_siembra', 'cierre_estimado', 'puesto', 'idoneidad', 'resultado')
    list_filter = ('resultado', 'cultivo')
    search_fields = ('cultivo', 'recomendacion__parcela__nombre')
    date_hierarchy = 'fecha_siembra'