"""
Módulo de Autenticación - Decoradores Locales de Control de Acceso por Roles (RBAC)
Funciona de forma directa y transparente con la sesión de Django (request.session)
y nuestra tabla propia 'Usuario', sin depender del sistema auth de Django.
"""

from functools import wraps
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.urls import reverse
from .models import Usuario

# Página de inicio de cada rol (a donde se devuelve a quien entra a una sección que no le corresponde)
INICIO_POR_ROL = {
    'admin': 'portal_dashboard',
    'docente': 'portal_dashboard',
    'recepcion': 'portal_recepcion',
    'tecnico': 'portal_taller',
}


def obtener_usuario_actual(request):
    """
    Obtiene la instancia del Usuario logueado a partir de su ID en la sesión.
    Si no hay sesión activa, retorna None.
    """
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return None
    try:
        return Usuario.objects.get(id=usuario_id, activo=True)
    except Usuario.DoesNotExist:
        return None


def obtener_rol_usuario(request):
    """
    Retorna el rol guardado en la sesión ('admin', 'docente', 'recepcion', 'tecnico').
    Si no hay sesión, retorna None.
    """
    return request.session.get('usuario_rol')


def roles_permitidos(lista_roles):
    """
    Decorador para proteger las vistas HTML del portal.
    1. Si el usuario no ha iniciado sesión, lo redirige al formulario de Login.
    2. Si es 'admin', tiene acceso irrestricto a todo el sistema.
    3. Si su rol coincide con 'lista_roles', permite el acceso.
    4. De lo contrario, lo devuelve automáticamente a su área de trabajo.
    """
    def decorador(vista_func):
        @wraps(vista_func)
        def envoltorio(request, *args, **kwargs):
            # 1. Comprobamos si hay sesión activa en la base de datos local
            usuario = obtener_usuario_actual(request)
            if not usuario:
                return redirect('portal_login')

            # 2. El Administrador siempre tiene pase universal
            if usuario.rol == 'admin':
                return vista_func(request, *args, **kwargs)

            # 3. Validamos si su rol está autorizado
            if usuario.rol in lista_roles:
                return vista_func(request, *args, **kwargs)

            # 4. Si no está autorizado, lo devolvemos a su área de trabajo (la página muestra un aviso breve)
            destino = reverse(INICIO_POR_ROL.get(usuario.rol, 'portal_login'))
            return redirect(f'{destino}?aviso=sin-acceso')

        return envoltorio
    return decorador


def api_roles_permitidos(lista_roles):
    """
    Decorador para proteger los endpoints de la API REST JSON.
    Retorna código HTTP 401 si no está autenticado, o 403 si su rol no tiene permiso.
    """
    def decorador(vista_func):
        @wraps(vista_func)
        def envoltorio(request, *args, **kwargs):
            usuario = obtener_usuario_actual(request)
            if not usuario:
                return JsonResponse({'error': 'No autenticado. Por favor inicie sesión.'}, status=401)

            if usuario.rol == 'admin' or usuario.rol in lista_roles:
                return vista_func(request, *args, **kwargs)

            return JsonResponse({
                'error': f'Acceso denegado: tu rol ({usuario.rol}) no está autorizado para esta operación.'
            }, status=403)

        return envoltorio
    return decorador
