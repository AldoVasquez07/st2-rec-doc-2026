from django.contrib import admin

from .models import ActualizacionClima, RegistroClima


@admin.register(RegistroClima)
class RegistroClimaAdmin(admin.ModelAdmin):
    list_display = ('distrito', 'fecha', 'temp_media', 'humedad', 'precipitacion', 'fuente')
    list_filter = ('distrito',)
    date_hierarchy = 'fecha'


@admin.register(ActualizacionClima)
class ActualizacionClimaAdmin(admin.ModelAdmin):
    list_display = ('distrito', 'fecha', 'exito', 'registros', 'mensaje')
    list_filter = ('exito', 'distrito')
