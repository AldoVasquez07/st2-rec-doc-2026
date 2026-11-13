from django.urls import path

from . import views

app_name = 'parcelas'

urlpatterns = [
    path('', views.ParcelaListView.as_view(), name='lista'),
    path('nueva/', views.ParcelaCreateView.as_view(), name='crear'),
    path('<int:pk>/editar/', views.ParcelaUpdateView.as_view(), name='editar'),
    path('<int:pk>/eliminar/', views.ParcelaDeleteView.as_view(), name='eliminar'),
]