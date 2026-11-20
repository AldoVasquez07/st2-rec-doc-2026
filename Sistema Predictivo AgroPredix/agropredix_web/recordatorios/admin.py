from django.contrib import admin

from .models import PreferenciaRecordatorio, Recordatorio, SuscripcionPush

admin.site.register(PreferenciaRecordatorio)
admin.site.register(Recordatorio)
admin.site.register(SuscripcionPush)