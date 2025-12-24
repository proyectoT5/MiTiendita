# MiTiendita/MiTiendita/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')), # Opcional
    path('', include('usuarios.urls')), 
    path('', include('tienda.urls')), # Aquí es donde está tu ruta personalizada
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)