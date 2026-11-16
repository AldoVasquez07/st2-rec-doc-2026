from django.contrib import admin

from .models import Recomendacion


@admin.register(Recomendacion)
class RecomendacionAdmin(admin.ModelAdmin):
    list_display = ('parcela', 'mes', 'antecesor', 'fecha')
    list_filter = ('mes',)