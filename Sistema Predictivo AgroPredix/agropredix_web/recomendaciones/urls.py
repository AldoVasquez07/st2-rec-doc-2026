from django.urls import path

from . import views

app_name = 'recomendaciones'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('parcela/<int:pk>/', views.generar, name='generar'),
    path('siembras/', views.seguimiento_lista, name='seguimiento'),
    path('siembras/<int:spk>/valorar/', views.valorar, name='valorar'),
    path('<int:rpk>/', views.detalle, name='detalle'),
    path('<int:rpk>/sembrar/<str:cod>/', views.sembrar, name='sembrar'),
]