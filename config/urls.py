"""
Configuración global de URLs del proyecto Clínica del PC.
No se utiliza el admin nativo de Django; la autenticación y gestión se realiza de forma local.
"""

from django.urls import path, include

urlpatterns = [
    # Endpoints de la API REST local (comunicación con la base de datos en formato JSON)
    path('api/', include('api.urls')),

    # Módulo de interfaz web (páginas HTML)
    path('', include('portal.urls')),
]
