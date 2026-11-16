from django.contrib import admin

from .models import Distrito, HistorialCampana, Parcela

admin.site.register(Distrito)
admin.site.register(Parcela)
admin.site.register(HistorialCampana)