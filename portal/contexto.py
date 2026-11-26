"""
Procesador de contexto: asegura que el navegador reciba la cookie con el token CSRF en todas las páginas,
para que las peticiones fetch que modifican datos puedan enviarlo en la cabecera X-CSRFToken.
"""

from django.middleware.csrf import get_token


def token_csrf(request):
    get_token(request)
    return {}
