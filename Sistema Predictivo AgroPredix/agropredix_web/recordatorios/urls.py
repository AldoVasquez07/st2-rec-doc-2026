from django.urls import path

from . import views

app_name = 'recordatorios'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('preferencias/', views.preferencias, name='preferencias'),
    path('suscribir/', views.suscribir, name='suscribir'),
]