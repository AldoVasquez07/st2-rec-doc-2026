from django.contrib import admin
from django.urls import path, include
from usuarios.views import HomeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuenta/', include('usuarios.urls')),
    path('parcelas/', include('parcelas.urls')),
    path('recomendaciones/', include('recomendaciones.urls')),
    path('', include('pwa.urls')),
    path('', HomeView.as_view(), name='home'),
]