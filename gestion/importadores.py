"""
Importadores masivos por CSV: usuarios (docentes y técnicos) y plantillas de checklist.

Cada importador tiene dos pasos:
  1. Previsualizar: revisa el archivo y dice qué pasaría con cada fila (no guarda nada).
  2. Confirmar: guarda en la base de datos solo las filas válidas.
"""

import csv
import io
import re
import secrets
import unicodedata

from django.db import transaction

from autenticacion.models import Usuario
from .models import PlantillaChecklist, TIPOS_SERVICIO

# Roles que se pueden crear por CSV (el admin NO se crea masivamente a propósito)
ROLES_IMPORTABLES = {
    'docente': 'docente',
    'profesor': 'docente',
    'tecnico': 'tecnico',
    'alumno': 'tecnico',
}

CABECERA_USUARIOS = ['nombre_usuario', 'nombre_completo', 'correo', 'rol', 'telefono', 'contrasena']
CABECERA_CHECKLISTS = ['tipo_servicio', 'codigo', 'descripcion']

# Nombres alternativos aceptados en las cabeceras (ya normalizados)
ALIAS_COLUMNAS = {
    'usuario': 'nombre_usuario',
    'nombre': 'nombre_completo',
    'email': 'correo',
    'mail': 'correo',
    'clave': 'contrasena',
    'password': 'contrasena',
    'telefono_celular': 'telefono',
    'servicio': 'tipo_servicio',
    'tipo': 'tipo_servicio',
    'item': 'codigo',
    'codigo_item': 'codigo',
    'tarea': 'descripcion',
}

EXPRESION_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
EXPRESION_USUARIO = re.compile(r'^[A-Za-z0-9._-]{3,50}$')


def _sin_tildes(texto):
    texto = unicodedata.normalize('NFD', texto)
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn')


def _normalizar_columna(nombre):
    nombre = _sin_tildes(nombre.strip().lower()).replace(' ', '_')
    return ALIAS_COLUMNAS.get(nombre, nombre)


def leer_csv(archivo_bytes, columnas_requeridas):
    """
    Lee un CSV (UTF-8 o Latin-1, separado por coma, punto y coma o tabulador).
    Retorna (filas, error). Cada fila es un dict con las columnas normalizadas
    más la clave '_fila' con el número de fila en el archivo.
    """
    try:
        texto = archivo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = archivo_bytes.decode('latin-1')

    if not texto.strip():
        return None, 'El archivo está vacío.'

    # Detectamos el separador mirando la primera línea (Excel en Chile usa ';')
    primera_linea = texto.splitlines()[0]
    separador = max([',', ';', '\t'], key=primera_linea.count)

    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    try:
        cabecera = [_normalizar_columna(c) for c in next(lector)]
    except StopIteration:
        return None, 'El archivo está vacío.'

    faltantes = [c for c in columnas_requeridas if c not in cabecera]
    if faltantes:
        return None, 'Faltan columnas obligatorias: ' + ', '.join(faltantes) + '.'

    filas = []
    for numero, valores in enumerate(lector, start=2):
        if not any(v.strip() for v in valores):
            continue  # ignoramos líneas en blanco
        fila = {col: (valores[i].strip() if i < len(valores) else '') for i, col in enumerate(cabecera)}
        fila['_fila'] = numero
        filas.append(fila)

    if not filas:
        return None, 'El archivo no tiene filas de datos.'
    return filas, None


def generar_clave():
    """Clave inicial aleatoria de 8 caracteres (sin letras confusas como l, 1, O, 0)."""
    alfabeto = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alfabeto) for _ in range(8))


def _resumen(resultados):
    resumen = {'nuevo': 0, 'omitido': 0, 'error': 0}
    for r in resultados:
        resumen[r['estado']] += 1
    return resumen


# ==============================================================================
# USUARIOS
# ==============================================================================

def procesar_usuarios(archivo_bytes, confirmar=False):
    filas, error = leer_csv(archivo_bytes, ['nombre_usuario', 'nombre_completo', 'rol'])
    if error:
        return {'error': error}

    existentes = set(Usuario.objects.values_list('nombre_usuario', flat=True))
    vistos = set()
    resultados = []

    for f in filas:
        usuario = f['nombre_usuario']
        rol = ROLES_IMPORTABLES.get(_sin_tildes(f['rol'].lower()))
        correo = f.get('correo', '')
        estado, motivo = 'nuevo', 'Se creará'

        if not EXPRESION_USUARIO.match(usuario):
            estado, motivo = 'error', 'Usuario inválido (3 a 50 caracteres: letras, números, . _ -)'
        elif not f['nombre_completo']:
            estado, motivo = 'error', 'Falta el nombre completo'
        elif rol is None:
            estado, motivo = 'error', 'Rol inválido (use docente o tecnico)'
        elif correo and not EXPRESION_CORREO.match(correo):
            estado, motivo = 'error', 'Correo con formato inválido'
        elif usuario in vistos:
            estado, motivo = 'error', 'Usuario repetido dentro del archivo'
        elif usuario in existentes:
            estado, motivo = 'omitido', 'Ya existe en el sistema'

        vistos.add(usuario)
        resultados.append({
            'fila': f['_fila'],
            'nombre_usuario': usuario,
            'nombre_completo': f['nombre_completo'],
            'rol': rol or f['rol'],
            'correo': correo,
            'estado': estado,
            'motivo': motivo,
            '_datos': f,
        })

    if confirmar:
        with transaction.atomic():
            for r in resultados:
                if r['estado'] != 'nuevo':
                    continue
                f = r['_datos']
                clave = f.get('contrasena', '') or generar_clave()
                u = Usuario(
                    nombre_usuario=r['nombre_usuario'],
                    nombre_completo=r['nombre_completo'],
                    correo=r['correo'],
                    rol=r['rol'],
                    telefono=f.get('telefono', ''),
                )
                u.fijar_contrasena(clave)
                u.save()
                r['clave_inicial'] = clave
                r['motivo'] = 'Creado'

    for r in resultados:
        r.pop('_datos')
    return {'confirmado': confirmar, 'resumen': _resumen(resultados), 'filas': resultados}


# ==============================================================================
# CHECKLISTS
# ==============================================================================

def procesar_checklists(archivo_bytes, confirmar=False):
    filas, error = leer_csv(archivo_bytes, ['tipo_servicio', 'codigo', 'descripcion'])
    if error:
        return {'error': error}

    servicios = {_sin_tildes(clave.lower()): clave for clave, _ in TIPOS_SERVICIO}
    vistos = set()
    resultados = []

    for f in filas:
        servicio = servicios.get(_sin_tildes(f['tipo_servicio'].lower()))
        codigo = f['codigo']
        estado, motivo = 'nuevo', 'Se cargará'

        if servicio is None:
            estado, motivo = 'error', 'Tipo de servicio inválido (Mantención Física, Mantención Lógica o Formateo)'
        elif not codigo or len(codigo) > 20:
            estado, motivo = 'error', 'Código vacío o de más de 20 caracteres'
        elif not f['descripcion']:
            estado, motivo = 'error', 'Falta la descripción'
        elif (servicio, codigo) in vistos:
            estado, motivo = 'error', 'Código repetido para este servicio'

        vistos.add((servicio, codigo))
        resultados.append({
            'fila': f['_fila'],
            'tipo_servicio': servicio or f['tipo_servicio'],
            'codigo': codigo,
            'descripcion': f['descripcion'],
            'estado': estado,
            'motivo': motivo,
        })

    if confirmar:
        validas = [r for r in resultados if r['estado'] == 'nuevo']
        # La plantilla de cada servicio incluido en el archivo se reemplaza completa.
        # Las órdenes que ya existen conservan sus checklists actuales.
        servicios_incluidos = {r['tipo_servicio'] for r in validas}
        with transaction.atomic():
            PlantillaChecklist.objects.filter(tipo_servicio__in=servicios_incluidos).delete()
            contador = {}
            for r in validas:
                contador[r['tipo_servicio']] = contador.get(r['tipo_servicio'], 0) + 1
                PlantillaChecklist.objects.create(
                    tipo_servicio=r['tipo_servicio'],
                    codigo=r['codigo'],
                    descripcion=r['descripcion'],
                    posicion=contador[r['tipo_servicio']],
                )
                r['motivo'] = 'Cargado'

    return {'confirmado': confirmar, 'resumen': _resumen(resultados), 'filas': resultados}
