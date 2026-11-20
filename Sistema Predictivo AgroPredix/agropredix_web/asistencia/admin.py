from django.contrib import admin

from .models import SolicitudAsistencia


@admin.register(SolicitudAsistencia)
class SolicitudAsistenciaAdmin(admin.ModelAdmin):
    """El especialista responde desde aquí (entra con una cuenta de rol especialista con acceso al admin)."""
    list_display = ('usuario', 'descripcion_corta', 'parcela', 'estado', 'creada', 'respondida_por')
    list_filter = ('estado',)
    search_fields = ('descripcion', 'usuario__nombre')
    readonly_fields = ('usuario', 'parcela', 'recomendacion', 'descripcion', 'creada', 'fecha_respuesta', 'respondida_por')
    fields = ('usuario', 'parcela', 'recomendacion', 'descripcion', 'creada',
              'estado', 'respuesta', 'respondida_por', 'fecha_respuesta')

    @admin.display(description='Consulta')
    def descripcion_corta(self, obj):
        return obj.descripcion[:60]

    def save_model(self, request, obj, form, change):
        if 'respuesta' in form.changed_data and obj.respuesta.strip():
            obj.respondida_por = request.user
        super().save_model(request, obj, form, change)
