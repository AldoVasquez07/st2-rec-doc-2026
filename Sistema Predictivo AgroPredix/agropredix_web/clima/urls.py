from django.urls import path

from . import views

app_name = 'clima'

urlpatterns = [
    path('parcela/<int:pk>/', views.clima_parcela, name='parcela'),
]
