from django.contrib import admin

from .models import Cultivo


@admin.register(Cultivo)
class CultivoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'grupo', 'tipo', 'familia', 'es_leguminosa', 'activo')
    list_filter = ('grupo', 'tipo', 'es_leguminosa', 'activo')
    search_fields = ('nombre',)