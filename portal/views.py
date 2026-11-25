"""
Módulo Portal - Vistas HTML del Prototipo con Autenticación Propia y RBAC
El Panel principal (Dashboard) es de acceso exclusivo para el Docente Supervisor y Administrador.
Los demás roles son dirigidos directamente a su lugar de trabajo:
- Recepción: /recepcion/
- Técnico: /taller/
"""

from django.shortcuts import render, redirect
from autenticacion.decoradores import (
    roles_permitidos, 
    obtener_usuario_actual, 
    obtener_rol_usuario
)

def vista_login(request):
    """Muestra el formulario de inicio de sesión"""
    usuario = obtener_usuario_actual(request)
    if usuario:
        # Redirigimos al usuario según su rol de trabajo
        if usuario.rol == 'tecnico':
            return redirect('portal_taller')
        elif usuario.rol == 'recepcion':
            return redirect('portal_recepcion')
        elif usuario.rol in ['docente', 'admin']:
            return redirect('portal_dashboard')

    return render(request, 'login.html')


def vista_preinscripcion(request):
    """
    Página pública de pre-inscripción vía código QR para los propietarios.
    No requiere login para que cualquier usuario de la comunidad pueda registrarse.
    Si entra un técnico o recepcionista logueado, lo envía a su área de trabajo.
    """
    usuario = obtener_usuario_actual(request)
    if usuario:
        if usuario.rol == 'tecnico':
            return redirect('portal_taller')
        elif usuario.rol == 'recepcion':
            return redirect('portal_recepcion')
        elif usuario.rol in ['docente', 'admin']:
            return redirect('portal_dashboard')

    return render(request, 'preinscripcion.html', {'modulo_activo': 'preinscripcion'})


def vista_dashboard(request):
    """
    Panel de Control principal con métricas en tiempo real.
    ACCESO EXCLUSIVO: Reservado únicamente para el Docente Supervisor y el Administrador.
    Si no hay sesión iniciada, se envía a iniciar sesión.
    Si un técnico o recepcionista intenta acceder, es enviado directamente a su módulo de trabajo.
    """
    usuario = obtener_usuario_actual(request)
    if not usuario:
        return redirect('portal_login')

    # Redirecciones automáticas para perfiles operativos a su área de trabajo
    if usuario.rol == 'tecnico':
        return redirect('portal_taller')
    elif usuario.rol == 'recepcion':
        return redirect('portal_recepcion')
    elif usuario.rol not in ['docente', 'admin']:
        return redirect('portal_login')

    return render(request, 'index.html', {
        'modulo_activo': 'dashboard',
        'rol_usuario': usuario.rol,
        'usuario': usuario
    })


@roles_permitidos(['recepcion', 'admin'])
def vista_recepcion(request):
    """
    Módulo 2-3: Mesón de Recepción y Constatación Inicial.
    Reservado para: Mesón de Recepción y Administrador.
    """
    return render(request, 'recepcion.html', {'modulo_activo': 'recepcion'})


@roles_permitidos(['tecnico', 'docente', 'admin'])
def vista_taller(request):
    """
    Módulo 4-5: Taller Técnico (Tablero Kanban y Checklists).
    Reservado para: Alumno Técnico, Docente Supervisor y Administrador.
    """
    return render(request, 'taller.html', {'modulo_activo': 'taller'})


@roles_permitidos(['docente', 'admin'])
def vista_calidad(request):
    """
    Módulo 6: V°B° y Certificación Docente de Control de Calidad.
    Reservado exclusivamente para: Docente Supervisor y Administrador.
    """
    return render(request, 'control_calidad.html', {'modulo_activo': 'control_calidad'})


@roles_permitidos(['recepcion', 'admin'])
def vista_entrega(request):
    """
    Módulo 7-9: Retiro, Comprobación con el usuario y Cierre de Orden.
    Reservado para: Mesón de Recepción y Administrador.
    """
    return render(request, 'entrega.html', {'modulo_activo': 'entrega'})


@roles_permitidos(['docente', 'admin'])
def vista_metricas(request):
    """
    Módulo de Estadísticas y Reportes Docentes.
    Reservado exclusivamente para: Docente Supervisor y Administrador.
    """
    return render(request, 'metricas.html', {'modulo_activo': 'metricas'})
