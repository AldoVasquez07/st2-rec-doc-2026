from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
def manifest(request):
    """Manifiesto de la PWA: lo que permite instalar AgroPredix en el celular (RF-0015)."""
    datos = {
        'id': '/',
        'name': 'AgroPredix',
        'short_name': 'AgroPredix',
        'description': 'Recomendaciones de siembra y rotación de cultivos para los valles de Arequipa.',
        'lang': 'es-PE',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#f8f9fa',
        'theme_color': '#198754',
        'icons': [
            {'src': static('pwa/icon-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('pwa/icon-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('pwa/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png',
             'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': 'Mis recomendaciones', 'url': '/recomendaciones/'},
            {'name': 'Mis parcelas', 'url': '/parcelas/'},
        ],
    }
    return JsonResponse(datos, json_dumps_params={'ensure_ascii': False},
                        content_type='application/manifest+json')


@require_GET
@never_cache
def service_worker(request):
    """El service worker se sirve desde la raíz (/service-worker.js) para que controle todo el sitio."""
    respuesta = render(request, 'pwa/service-worker.js', {'version': settings.PWA_VERSION},
                       content_type='text/javascript; charset=utf-8')
    respuesta['Service-Worker-Allowed'] = '/'
    return respuesta


@require_GET
def sin_conexion(request):
    """Página que se muestra cuando no hay internet y lo pedido no estaba guardado."""
    return render(request, 'pwa/offline.html')