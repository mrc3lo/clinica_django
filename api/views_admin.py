"""
Endpoints de Administración (solo rol admin): carga masiva por CSV de usuarios y checklists.
"""

import csv
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from autenticacion.decoradores import api_roles_permitidos
from autenticacion.models import Usuario
from gestion.importadores import (
    procesar_usuarios, procesar_checklists, CABECERA_USUARIOS, CABECERA_CHECKLISTS
)
from gestion.models import PlantillaChecklist, TIPOS_SERVICIO
from .views import CATALOGO_CHECKLISTS, obtener_catalogo_checklist


def _respuesta_csv(nombre_archivo, filas):
    """Arma un CSV descargable (UTF-8 con BOM y ';' para que Excel lo abra bien)."""
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    respuesta.write('﻿')
    escritor = csv.writer(respuesta, delimiter=';')
    for fila in filas:
        escritor.writerow(fila)
    return respuesta


@api_roles_permitidos(['admin'])
def api_plantilla_usuarios(request):
    """GET: CSV de ejemplo para cargar usuarios."""
    return _respuesta_csv('plantilla_usuarios.csv', [
        CABECERA_USUARIOS,
        ['mgonzalez', 'Marta González Rojas', 'mgonzalez@inacap.cl', 'docente', '+56 9 1111 2222', ''],
        ['jperez', 'Juan Pérez Soto', 'jperez@alumnos.inacap.cl', 'tecnico', '', ''],
    ])


@api_roles_permitidos(['admin'])
def api_plantilla_checklists(request):
    """GET: CSV de ejemplo para cargar checklists (precargado con la plantilla vigente)."""
    filas = [CABECERA_CHECKLISTS]
    for servicio, _ in TIPOS_SERVICIO:
        for codigo, descripcion in obtener_catalogo_checklist(servicio):
            filas.append([servicio, codigo, descripcion])
    return _respuesta_csv('plantilla_checklists.csv', filas)


def _importar(request, procesador):
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'error': 'Debe adjuntar un archivo CSV.'}, status=400)
    if archivo.size > 2 * 1024 * 1024:
        return JsonResponse({'error': 'El archivo supera los 2 MB.'}, status=400)
    confirmar = request.POST.get('confirmar') == '1'
    resultado = procesador(archivo.read(), confirmar=confirmar)
    if 'error' in resultado:
        return JsonResponse(resultado, status=400)
    return JsonResponse(resultado)


@csrf_exempt
@api_roles_permitidos(['admin'])
def api_importar_usuarios(request):
    """POST (multipart): archivo CSV y confirmar=0|1."""
    return _importar(request, procesar_usuarios)


@csrf_exempt
@api_roles_permitidos(['admin'])
def api_importar_checklists(request):
    """POST (multipart): archivo CSV y confirmar=0|1."""
    return _importar(request, procesar_checklists)


@api_roles_permitidos(['admin'])
def api_listar_usuarios(request):
    """GET: usuarios del sistema (sin contraseñas)."""
    usuarios = Usuario.objects.all()
    return JsonResponse({'usuarios': [
        {
            'id': u.id,
            'nombre_usuario': u.nombre_usuario,
            'nombre_completo': u.nombre_completo,
            'correo': u.correo,
            'rol': u.rol,
            'rol_legible': u.get_rol_display(),
            'activo': u.activo,
        } for u in usuarios
    ]})


@api_roles_permitidos(['admin'])
def api_listar_plantillas(request):
    """GET: plantilla vigente por servicio y si viene del CSV o del catálogo por defecto."""
    resultado = []
    for servicio, _ in TIPOS_SERVICIO:
        cargada = PlantillaChecklist.objects.filter(tipo_servicio=servicio).exists()
        resultado.append({
            'tipo_servicio': servicio,
            'origen': 'CSV' if cargada else 'Por defecto',
            'items': [{'codigo': c, 'descripcion': d} for c, d in obtener_catalogo_checklist(servicio)],
        })
    return JsonResponse({'plantillas': resultado})
