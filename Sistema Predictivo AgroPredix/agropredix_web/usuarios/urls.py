from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('ingresar/', views.IngresarView.as_view(), name='login'),
    path('salir/', LogoutView.as_view(), name='logout'),
    path('registro/', views.RegistroView.as_view(), name='registro'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),
    path('perfil/clave/', views.CambiarClaveView.as_view(), name='cambiar_clave'),
    path('perfil/eliminar/', views.EliminarCuentaView.as_view(), name='eliminar_cuenta'),
]