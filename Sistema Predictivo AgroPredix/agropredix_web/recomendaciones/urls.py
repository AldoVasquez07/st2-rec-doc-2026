from django.urls import path

from . import views

app_name = 'recomendaciones'

urlpatterns = [
    path('parcela/<int:pk>/', views.generar, name='generar'),
    path('<int:rpk>/', views.detalle, name='detalle'),
]