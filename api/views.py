"""
Módulo API REST - Endpoints JSON con Autenticación Local Propia
No depende de django.contrib.auth. Utiliza la tabla propia 'Usuario' en SQLite
y el manejo de sesiones estándar de Django (request.session).
"""

import json
import logging
import re
import unicodedata
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction

# Importamos nuestro modelo propio de Usuario y utilidades de sesión
from autenticacion.models import Usuario
from autenticacion.decoradores import obtener_usuario_actual, obtener_rol_usuario, api_roles_permitidos
from gestion.models import (
    Propietario, 
    Dispositivo, 
    OrdenServicio, 
    ItemChecklist, 
    ObservacionOrden, 
    VistoBuenoDocente, 
    EvaluacionSatisfaccion,
    PlantillaChecklist,
    ESTADOS_ORDEN,
    TIPOS_DISPOSITIVO,
    normalizar_servicios
)
from gestion.validadores import (
    validar_rut, formatear_rut, enmascarar_rut, validar_telefono, validar_correo,
    texto_seguro, MAX_NOMBRE, MAX_TEXTO_CORTO, MAX_TEXTO_LARGO
)

# Bitácora de seguridad (OWASP A09): intentos de login fallidos, bloqueos y acciones sensibles
registro = logging.getLogger('clinica')

# Roles del personal que puede usar la API (el administrador siempre tiene pase)
ROLES_PERSONAL = ['recepcion', 'docente', 'tecnico']
ESTADOS_VALIDOS = [e for e, _ in ESTADOS_ORDEN]
TIPOS_DISPOSITIVO_VALIDOS = [t for t, _ in TIPOS_DISPOSITIVO]
CRITICIDADES_VALIDAS = ('Baja', 'Media', 'Alta')

# Protección contra fuerza bruta en el login: 5 intentos fallidos por usuario y equipo cada 15 minutos
MAX_INTENTOS_LOGIN = 5
VENTANA_BLOQUEO_SEGUNDOS = 15 * 60

# Catálogo estándar de checklists según el informe técnico de INACAP
CATALOGO_CHECKLISTS = {
    'Mantención Física': [
        ('F-01', 'Inspección y Apertura: Verificación de pernos de chasis y desmontaje seguro'),
        ('F-02', 'Limpieza y Desempolvado: Soplado de coolers y disipador térmico'),
        ('F-03', 'Renovación Térmica: Limpieza y cambio de pasta térmica en CPU/GPU'),
        ('F-04', 'Puertos e Interfaces: Limpieza y desoxidación de puertos I/O'),
        ('F-05', 'Reensamblaje y Torque: Cierre de chasis y torque de tornillos'),
    ],
    'Mantención Lógica': [
        ('L-01', 'Depuración de Almacenamiento: Eliminación de temporales (%temp%) y liberador'),
        ('L-02', 'Optimización de Inicio: Desactivación de apps redundantes y bloatware'),
        ('L-03', 'Seguridad y Malware: Escaneo completo antivirus y antimalware'),
        ('L-04', 'Integridad de Sistema: Comprobación con sfc /scannow y DISM'),
        ('L-05', 'Controladores y Actualizaciones: Actualización de drivers críticos'),
    ],
    'Formateo': [
        ('R-01', 'Verificación de Respaldo: Comprobación obligatoria de consentimiento'),
        ('R-02', 'Configuración de Arranque: Ajuste UEFI/BIOS y Secure Boot'),
        ('R-03', 'Particionamiento e Instalación: Limpieza e instalación limpia de SO'),
        ('R-04', 'Paquetería Base: Instalación de utilitarios base y ofimática'),
        ('R-05', 'Comprobación Funcional: Reconocimiento de drivers y activación'),
    ]
}


def obtener_catalogo_checklist(tipo_servicio):
    """
    Retorna la lista (codigo, descripcion) de checklist para un tipo de servicio.
    Usa la plantilla cargada por CSV; si no hay ninguna, usa el catálogo por defecto.
    """
    plantilla = PlantillaChecklist.objects.filter(tipo_servicio=tipo_servicio)
    if plantilla.exists():
        return [(p.codigo, p.descripcion) for p in plantilla]
    return CATALOGO_CHECKLISTS.get(tipo_servicio, [])


def _sin_tildes_minusculas(texto):
    texto = unicodedata.normalize('NFD', texto or '')
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn').lower()


def titular_coincide(propietario, texto):
    """
    True si el texto buscado coincide con el titular:
    - por nombre: todas las palabras escritas aparecen en el nombre (sin importar tildes ni mayúsculas)
    - por RUT: si el texto tiene algún número, se compara sin puntos ni guion
    """
    nombre = _sin_tildes_minusculas(propietario.nombre_completo)
    palabras = _sin_tildes_minusculas(texto).split()
    if palabras and all(p in nombre for p in palabras):
        return True
    if any(c.isdigit() for c in texto):
        rut_buscado = re.sub(r'[^0-9kK]', '', texto).lower()
        rut_titular = re.sub(r'[^0-9kK]', '', propietario.rut).lower()
        return bool(rut_buscado) and rut_buscado in rut_titular
    return False


def orden_oculta_para_tecnico(usuario, orden):
    """
    Un técnico solo ve las órdenes recepcionadas en espera y las que él mismo atiende.
    Las de otros técnicos (en mantención, pausadas o terminadas) le quedan ocultas.
    """
    if not usuario or usuario.rol != 'tecnico':
        return False
    if orden.estado == 'Recepcionado':
        return False
    return (orden.tecnico_asignado or '').strip().lower() != usuario.nombre_completo.strip().lower()


def respuesta_orden_ajena():
    return JsonResponse({'error': 'Esta orden está asignada a otro técnico.'}, status=403)


def obtener_catalogo_para_servicios(servicios):
    """Junta los checklists de todos los servicios de la orden (sin repetir códigos)."""
    items, codigos = [], set()
    for servicio in servicios:
        for codigo, descripcion in obtener_catalogo_checklist(servicio):
            if codigo not in codigos:
                codigos.add(codigo)
                items.append((codigo, descripcion))
    return items


def sincronizar_checklist(orden):
    """
    Ajusta el checklist de una orden cuando cambian sus servicios:
    agrega los ítems que faltan y quita los que quedaron PENDIENTES y ya no corresponden.
    Los ítems ya revisados (OK, FALLA, N/A) nunca se borran.
    """
    catalogo = obtener_catalogo_para_servicios(orden.servicios)
    codigos = {codigo for codigo, _ in catalogo}
    orden.items_checklist.filter(resultado='PENDIENTE').exclude(codigo_item__in=codigos).delete()
    existentes = set(orden.items_checklist.values_list('codigo_item', flat=True))
    for codigo, descripcion in catalogo:
        if codigo not in existentes:
            ItemChecklist.objects.create(orden=orden, codigo_item=codigo, descripcion=descripcion, resultado='PENDIENTE')


def servicios_desde_datos(datos, por_defecto=None):
    """Lee 'servicios' (lista) o 'tipoServicio' (texto) del JSON recibido."""
    bruto = datos.get('servicios', datos.get('tipoServicio'))
    lista = normalizar_servicios(bruto)
    return lista or (por_defecto if por_defecto is not None else ['Mantención Física'])


def validar_datos_titular(rut, nombre, telefono, email):
    """Valida los datos del titular en el servidor. Devuelve el mensaje de error o None si todo está bien."""
    if not rut or not nombre:
        return 'El RUT y el Nombre del titular son obligatorios.'
    if not validar_rut(rut):
        return 'El RUT no es válido (revise el número y el dígito verificador).'
    if not validar_telefono(telefono):
        return 'El teléfono no tiene un formato válido.'
    if not validar_correo(email):
        return 'El correo electrónico no tiene un formato válido.'
    return None


def dic_orden(orden, usuario):
    """
    Convierte la orden a diccionario JSON aplicando la privacidad por rol (Ley 19.628):
    al técnico se le entrega el RUT enmascarado desde el servidor, no solo oculto en pantalla.
    """
    datos = orden.a_diccionario_completo()
    if usuario and usuario.rol == 'tecnico':
        datos['propietario']['rut'] = enmascarar_rut(datos['propietario']['rut'])
    return datos


def leer_json(request):
    """Lee el cuerpo JSON de la petición; si no es un objeto JSON válido, devuelve un diccionario vacío."""
    try:
        datos = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def ip_cliente(request):
    return request.META.get('REMOTE_ADDR', 'desconocida')


def error_interno(contexto):
    """
    Respuesta genérica para errores inesperados (OWASP A05/A09): el detalle técnico queda en la bitácora
    del servidor y no se le muestra al usuario, para no revelar la estructura interna del sistema.
    """
    registro.exception(contexto)
    return JsonResponse({'error': 'Ocurrió un error interno. Intente nuevamente.'}, status=500)


# ==============================================================================
# ENDPOINTS DE AUTENTICACIÓN LOCAL PROPIA
# ==============================================================================

def api_iniciar_sesion(request):
    """
    POST: Valida credenciales contra nuestra tabla local 'Usuario' en SQLite.
    Guarda en request.session el ID y rol del usuario, sin usar django-admin.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido. Use POST.'}, status=405)

    try:
        datos = leer_json(request)
        nombre_usuario = texto_seguro(datos.get('usuario'), 50)
        clave = texto_seguro(datos.get('clave'), 128)

        # Fuerza bruta (OWASP A07): se bloquea temporalmente tras varios intentos fallidos
        llave_intentos = f'login:{ip_cliente(request)}:{nombre_usuario.lower()}'
        if cache.get(llave_intentos, 0) >= MAX_INTENTOS_LOGIN:
            registro.warning('Login bloqueado por demasiados intentos: usuario=%s ip=%s', nombre_usuario, ip_cliente(request))
            return JsonResponse({
                'error': 'Demasiados intentos fallidos. Espere unos minutos antes de volver a intentar.'
            }, status=429)

        # Buscamos en nuestra tabla propia de usuarios
        usuario = Usuario.objects.filter(nombre_usuario=nombre_usuario, activo=True).first()

        if usuario and usuario.verificar_contrasena(clave):
            cache.delete(llave_intentos)
            # Se regenera la sesión al autenticar (evita la fijación de sesión)
            request.session.cycle_key()
            # Guardamos los datos directamente en la sesión de Django
            request.session['usuario_id'] = usuario.id
            request.session['usuario_rol'] = usuario.rol
            request.session['usuario_nombre'] = usuario.nombre_completo

            # Destino según su función:
            # - Docente y Administrador van al Panel Principal (Dashboard)
            # - Recepción va al Mesón de entrada
            # - Técnico va directo a su mesa de Taller
            destinos = {
                'admin': '/',
                'docente': '/',
                'recepcion': '/recepcion/',
                'tecnico': '/taller/'
            }
            url_destino = destinos.get(usuario.rol, '/login/')

            return JsonResponse({
                'mensaje': 'Inicio de sesión exitoso',
                'usuario': usuario.a_diccionario(),
                'url_destino': url_destino
            })
        else:
            cache.set(llave_intentos, cache.get(llave_intentos, 0) + 1, VENTANA_BLOQUEO_SEGUNDOS)
            registro.warning('Login fallido: usuario=%s ip=%s', nombre_usuario, ip_cliente(request))
            # Mensaje único: no revela si el usuario existe o si falló la contraseña
            return JsonResponse({
                'error': 'Usuario o contraseña incorrectos. Por favor verifique.'
            }, status=401)

    except Exception:
        return error_interno('Error en el proceso de login')


def api_cerrar_sesion(request):
    """POST: Limpia la sesión del usuario (solo POST, protegido con token CSRF)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)
    request.session.flush()
    return JsonResponse({'mensaje': 'Sesión cerrada correctamente'})


def api_usuario_actual(request):
    """GET: Retorna los datos del usuario conectado en la sesión activa."""
    usuario = obtener_usuario_actual(request)
    if usuario:
        return JsonResponse({
            'autenticado': True,
            'usuario': usuario.a_diccionario()
        })
    return JsonResponse({'autenticado': False, 'usuario': None})


# ==============================================================================
# ENDPOINTS DE PROPIETARIOS Y DISPOSITIVOS
# ==============================================================================

@api_roles_permitidos(['recepcion'])
def api_propietarios(request):
    """
    GET y POST para la gestión de propietarios.
    CONTROL DE ACCESO: contiene datos personales de terceros, por eso solo lo usa el Mesón de Recepción.
    """
    if request.method == 'GET':
        rut_buscar = request.GET.get('rut', '').strip()
        if rut_buscar:
            propietarios = Propietario.objects.filter(rut__icontains=rut_buscar)
        else:
            propietarios = Propietario.objects.all().order_by('-fecha_registro')

        return JsonResponse({'propietarios': [p.a_diccionario() for p in propietarios]})

    elif request.method == 'POST':
        try:
            datos = leer_json(request)
            rut = texto_seguro(datos.get('rut'), 20)
            nombre = texto_seguro(datos.get('nombre'), MAX_NOMBRE)
            telefono = texto_seguro(datos.get('telefono'), 30)
            email = texto_seguro(datos.get('email'), 254)
            comuna = texto_seguro(datos.get('comuna') or 'San Pedro de la Paz', MAX_TEXTO_CORTO)
            consentimiento = datos.get('consentimiento') is not False

            error_datos = validar_datos_titular(rut, nombre, telefono, email)
            if error_datos:
                return JsonResponse({'error': error_datos}, status=400)
            rut = formatear_rut(rut)

            propietario, creado = Propietario.objects.update_or_create(
                rut=rut,
                defaults={
                    'nombre_completo': nombre,
                    'telefono': telefono,
                    'correo': email,
                    'comuna': comuna,
                    'consentimiento_datos': consentimiento,
                }
            )

            return JsonResponse({
                'mensaje': 'Propietario registrado con éxito',
                'creado': creado,
                'propietario': propietario.a_diccionario()
            })
        except Exception:
            return error_interno('Error al registrar propietario')

    return JsonResponse({'error': 'Método no soportado'}, status=405)


@api_roles_permitidos(['recepcion'])
def api_dispositivos(request):
    """GET: Lista dispositivos en la base de datos (solo Recepción y Administrador)."""
    rut = request.GET.get('rut', '').strip()
    if rut:
        dispositivos = Dispositivo.objects.filter(propietario__rut__icontains=rut)
    else:
        dispositivos = Dispositivo.objects.all().order_by('-id')

    return JsonResponse({'dispositivos': [d.a_diccionario() for d in dispositivos]})


# ==============================================================================
# ENDPOINTS DE ÓRDENES DE SERVICIO
# ==============================================================================

def api_listar_o_crear_ordenes(request):
    """
    GET: Lista órdenes con filtros opcionales (requiere sesión iniciada).
    POST: Crea nueva orden. Es público solo para la pre-inscripción por QR (estado 'Preinscrito');
          el personal autenticado puede registrar otros datos (registro express en mesón).
    """
    usuario = obtener_usuario_actual(request)

    if request.method == 'GET':
        if not usuario:
            return JsonResponse({'error': 'No autenticado. Por favor inicie sesión.'}, status=401)
        filtro_estado = request.GET.get('estado', '').strip()
        filtro_rut = request.GET.get('rut', '').strip()
        filtro_servicio = request.GET.get('servicio', '').strip()

        queryset = OrdenServicio.objects.select_related('dispositivo', 'dispositivo__propietario').all()

        if filtro_estado:
            queryset = queryset.filter(estado=filtro_estado)
        if filtro_rut:
            queryset = queryset.filter(dispositivo__propietario__rut__icontains=filtro_rut)
        if filtro_servicio:
            queryset = queryset.filter(tipo_servicio__icontains=filtro_servicio)

        queryset = queryset.order_by('-id')
        ordenes = list(queryset)

        # Búsqueda libre por nombre o RUT del titular (ignora mayúsculas y tildes)
        filtro_q = request.GET.get('q', '').strip()
        if filtro_q:
            ordenes = [o for o in ordenes if titular_coincide(o.dispositivo.propietario, filtro_q)]

        # El técnico solo ve lo que está en espera y sus propios equipos
        ordenes = [o for o in ordenes if not orden_oculta_para_tecnico(usuario, o)]

        return JsonResponse({'ordenes': [dic_orden(orden, usuario) for orden in ordenes]})

    elif request.method == 'POST':
        try:
            with transaction.atomic():
                datos = leer_json(request)

                rut = texto_seguro(datos.get('rut'), 20)
                nombre = texto_seguro(datos.get('nombre'), MAX_NOMBRE)
                telefono = texto_seguro(datos.get('telefono'), 30)
                email = texto_seguro(datos.get('email'), 254)
                comuna = texto_seguro(datos.get('comuna') or 'San Pedro de la Paz', MAX_TEXTO_CORTO)

                error_datos = validar_datos_titular(rut, nombre, telefono, email)
                if error_datos:
                    return JsonResponse({'error': error_datos}, status=400)
                rut = formatear_rut(rut)

                # Consentimiento informado (Ley 19.628): sin aceptación expresa no se registran datos
                if datos.get('consentimiento') is not True:
                    return JsonResponse({'error': 'Debe aceptar el consentimiento informado para continuar.'}, status=400)

                datos_titular = {
                    'nombre_completo': nombre,
                    'telefono': telefono,
                    'correo': email,
                    'comuna': comuna,
                    'consentimiento_datos': True
                }
                if usuario:
                    propietario, _ = Propietario.objects.update_or_create(rut=rut, defaults=datos_titular)
                else:
                    # El público anónimo no puede sobrescribir los datos de un titular ya registrado
                    propietario, _ = Propietario.objects.get_or_create(rut=rut, defaults=datos_titular)

                total_equipos = Dispositivo.objects.count() + 1
                etiqueta = f"CLI-PC-2026-{total_equipos:04d}"

                tipo = datos.get('tipo') if datos.get('tipo') in TIPOS_DISPOSITIVO_VALIDOS else 'Notebook'
                marca = texto_seguro(datos.get('marca') or 'Genérico', MAX_TEXTO_CORTO)
                modelo = texto_seguro(datos.get('modelo') or 'Estándar', MAX_TEXTO_CORTO)
                numero_serie = texto_seguro(datos.get('numeroSerie'), 100)
                accesorios = texto_seguro(datos.get('accesorios') or 'Sin accesorios')

                dispositivo = Dispositivo.objects.create(
                    propietario=propietario,
                    tipo=tipo,
                    marca=marca,
                    modelo=modelo,
                    numero_serie=numero_serie,
                    etiqueta_taller=etiqueta,
                    accesorios=accesorios
                )

                servicios = servicios_desde_datos(datos)
                tipo_servicio = ', '.join(servicios)
                falla = texto_seguro(datos.get('fallaReportada') or 'Mantención preventiva solicitada')
                if usuario and usuario.rol in ('recepcion', 'admin'):
                    estado_inicial = datos.get('estado') if datos.get('estado') in ESTADOS_VALIDOS else 'Preinscrito'
                    encendido = datos.get('encendidoInicial', None)
                    inspeccion = texto_seguro(datos.get('detalleInspeccionPrevia'))
                    tecnico = None
                else:
                    # Público (QR) y otros perfiles: la orden siempre nace "Preinscrito" y sin datos de taller
                    estado_inicial, encendido, inspeccion, tecnico = 'Preinscrito', None, '', None

                orden = OrdenServicio.objects.create(
                    dispositivo=dispositivo,
                    etiqueta_taller=etiqueta,
                    estado=estado_inicial,
                    tipo_servicio=tipo_servicio,
                    falla_reportada=falla,
                    encendido_inicial=encendido,
                    detalle_inspeccion_previa=inspeccion,
                    tecnico_asignado=tecnico
                )

                items_plantilla = obtener_catalogo_para_servicios(servicios)
                for codigo, descripcion in items_plantilla:
                    ItemChecklist.objects.create(
                        orden=orden,
                        codigo_item=codigo,
                        descripcion=descripcion,
                        resultado='PENDIENTE'
                    )

                return JsonResponse({
                    'mensaje': 'Orden creada exitosamente',
                    'orden': dic_orden(orden, usuario)
                }, status=201)

        except Exception:
            return error_interno('Error al registrar la orden')

    return JsonResponse({'error': 'Método no soportado'}, status=405)


@api_roles_permitidos(ROLES_PERSONAL)
def api_detalle_orden(request, orden_id):
    """GET o PUT/POST: Consulta o actualiza campos de la orden (solo personal autenticado)."""
    try:
        orden = OrdenServicio.objects.select_related('dispositivo', 'dispositivo__propietario').get(id=orden_id)
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': f'No existe una orden con ID {orden_id}'}, status=404)

    usuario = obtener_usuario_actual(request)
    if orden_oculta_para_tecnico(usuario, orden):
        return respuesta_orden_ajena()

    if request.method == 'GET':
        return JsonResponse({'orden': dic_orden(orden, usuario)})

    elif request.method in ['PUT', 'POST']:
        try:
            datos = leer_json(request)
            # Solo se aceptan estados que existen en el flujo
            if 'estado' in datos and datos['estado'] not in ESTADOS_VALIDOS:
                return JsonResponse({'error': 'Estado de orden no válido.'}, status=400)
            # Una orden solo se recepciona una vez: debe venir desde "Preinscrito"
            if datos.get('estado') == 'Recepcionado' and orden.estado != 'Preinscrito':
                return JsonResponse({
                    'error': f'Esta orden ya fue recepcionada (estado actual: {orden.estado}).'
                }, status=409)
            if 'estado' in datos:
                orden.estado = datos['estado']
            if 'tecnicoAsignado' in datos and usuario.rol != 'tecnico':
                orden.tecnico_asignado = texto_seguro(datos['tecnicoAsignado'], 120) or None
            if 'encendidoInicial' in datos and (datos['encendidoInicial'] is None or isinstance(datos['encendidoInicial'], bool)):
                orden.encendido_inicial = datos['encendidoInicial']
            if 'detalleInspeccionPrevia' in datos:
                orden.detalle_inspeccion_previa = texto_seguro(datos['detalleInspeccionPrevia'])
            servicios_cambiaron = False
            if 'servicios' in datos or 'tipoServicio' in datos:
                nuevos = servicios_desde_datos(datos, por_defecto=orden.servicios)
                servicios_cambiaron = nuevos != orden.servicios
                orden.tipo_servicio = ', '.join(nuevos)
            if 'fallaReportada' in datos:
                orden.falla_reportada = texto_seguro(datos['fallaReportada'])
            if 'llamadaRealizada' in datos:
                orden.llamada_realizada = datos['llamadaRealizada'] is True

            # Datos del equipo: el número de serie lo registra el técnico en taller;
            # los accesorios los registra recepción al recibir el equipo.
            dispositivo = orden.dispositivo
            if 'numeroSerie' in datos:
                dispositivo.numero_serie = texto_seguro(datos['numeroSerie'], 100)
            if 'accesorios' in datos:
                dispositivo.accesorios = texto_seguro(datos['accesorios']) or 'Sin accesorios'
            if 'numeroSerie' in datos or 'accesorios' in datos:
                dispositivo.save()

            orden.save()
            if servicios_cambiaron:
                sincronizar_checklist(orden)
            return JsonResponse({
                'mensaje': 'Orden actualizada correctamente',
                'orden': dic_orden(orden, usuario)
            })
        except Exception:
            return error_interno('Error al actualizar orden')

    return JsonResponse({'error': 'Método no soportado'}, status=405)


@api_roles_permitidos(ROLES_PERSONAL)
def api_cambiar_estado_orden(request, orden_id):
    """POST: Cambia el estado de una orden en el flujo operativo."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        usuario = obtener_usuario_actual(request)
        if orden_oculta_para_tecnico(usuario, orden):
            return respuesta_orden_ajena()
        datos = leer_json(request)
        nuevo_estado = datos.get('estado')

        if not nuevo_estado:
            return JsonResponse({'error': 'Debe especificar el nuevo estado'}, status=400)
        if nuevo_estado not in ESTADOS_VALIDOS:
            return JsonResponse({'error': 'Estado de orden no válido.'}, status=400)

        orden.estado = nuevo_estado
        if nuevo_estado == 'Entregado Conforme' and not orden.fecha_cierre:
            orden.fecha_cierre = timezone.now()

        if 'tecnicoAsignado' in datos:
            orden.tecnico_asignado = texto_seguro(datos['tecnicoAsignado'], 120) or None
        # Si lo hace un técnico, el equipo queda siempre a su nombre (no se puede asignar a otro)
        if usuario and usuario.rol == 'tecnico':
            orden.tecnico_asignado = usuario.nombre_completo

        orden.save()

        registro.info('Cambio de estado: orden=%s nuevo_estado=%s por=%s', orden.id, nuevo_estado, usuario)
        return JsonResponse({
            'mensaje': f'Estado cambiado a "{nuevo_estado}"',
            'orden': dic_orden(orden, usuario)
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception:
        return error_interno('Error al cambiar el estado de la orden')


@api_roles_permitidos(['tecnico', 'docente'])
def api_actualizar_checklist(request, orden_id):
    """POST: Actualiza el resultado de un ítem de checklist."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        if orden_oculta_para_tecnico(usuario, orden):
            return respuesta_orden_ajena()
        datos = leer_json(request)
        codigo = texto_seguro(datos.get('codigo'), 20)
        resultado = datos.get('resultado', 'OK')
        descripcion = texto_seguro(datos.get('desc'), 250)
        motivo = texto_seguro(datos.get('motivo'))

        if not codigo:
            return JsonResponse({'error': 'El código del checklist es obligatorio'}, status=400)
        if resultado not in ('PENDIENTE', 'OK', 'FALLA', 'NO_APLICA'):
            return JsonResponse({'error': 'Resultado de checklist no válido'}, status=400)
        # Si un punto de control falla hay que explicar por qué
        if resultado == 'FALLA' and not motivo:
            return JsonResponse({'error': 'Debe indicar por qué falló este punto de control.'}, status=400)

        item, _ = ItemChecklist.objects.update_or_create(
            orden=orden,
            codigo_item=codigo,
            defaults={
                'resultado': resultado,
                'descripcion': descripcion if descripcion else f'Control {codigo}',
                'motivo_falla': motivo if resultado == 'FALLA' else ''
            }
        )

        return JsonResponse({
            'mensaje': 'Checklist actualizado',
            'item': {'codigo': item.codigo_item, 'resultado': item.resultado, 'motivo': item.motivo_falla}
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception:
        return error_interno('Error al actualizar el checklist')


@api_roles_permitidos(['tecnico', 'docente'])
def api_agregar_observacion(request, orden_id):
    """POST: Registra anotación en la bitácora técnica de la orden."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        if orden_oculta_para_tecnico(obtener_usuario_actual(request), orden):
            return respuesta_orden_ajena()
        datos = leer_json(request)
        texto = texto_seguro(datos.get('texto'))
        hallazgo_legal = datos.get('hallazgoLegal') is True
        # El autor sale de la sesión (no del navegador) para que la bitácora no se pueda suplantar
        autor = obtener_usuario_actual(request).nombre_completo
        criticidad = datos.get('criticidad') if datos.get('criticidad') in CRITICIDADES_VALIDAS else 'Baja'

        if not texto:
            return JsonResponse({'error': 'El texto de la observación no puede estar vacío'}, status=400)

        if hallazgo_legal:
            # Protocolo ante contenido ilegal: no se copia el contenido, se alerta al docente y se detiene el trabajo
            texto = f'[HALLAZGO LEGAL] {texto}'
            criticidad = 'Alta'
            orden.estado = 'Pausado'
            orden.save()
            registro.warning('Hallazgo legal reportado: orden=%s por=%s', orden.id, obtener_usuario_actual(request))

        obs = ObservacionOrden.objects.create(
            orden=orden,
            autor=autor,
            criticidad=criticidad,
            texto=texto
        )

        return JsonResponse({
            'mensaje': 'Observación guardada con éxito',
            'observacion': {
                'id': obs.id,
                'autor': obs.autor,
                'criticidad': obs.criticidad,
                'texto': obs.texto,
                'fecha': obs.fecha_registro.strftime('%Y-%m-%d %H:%M')
            }
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception:
        return error_interno('Error al guardar la observación')


@api_roles_permitidos(['docente'])
def api_guardar_visto_bueno(request, orden_id):
    """
    POST: Certificación y firma de Visto Bueno.
    CONTROL DE ACCESO LOCAL: Exclusivo para Docente Supervisor y Administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        datos = leer_json(request)
        # La firma del V°B° sale de la sesión: el docente no puede firmar a nombre de otro
        docente = usuario.nombre_completo
        comentario = texto_seguro(datos.get('comentario')) or 'Certificado en banco de prueba.'

        VistoBuenoDocente.objects.update_or_create(
            orden=orden,
            defaults={
                'docente_nombre': docente,
                'comentario': comentario,
                'fecha_aprobacion': timezone.now()
            }
        )

        orden.estado = 'Listo para Entrega'
        orden.save()

        registro.info('Visto bueno registrado: orden=%s docente=%s', orden.id, usuario)
        return JsonResponse({
            'mensaje': 'Visto Bueno Docente registrado. Orden lista para entrega.',
            'orden': dic_orden(orden, usuario)
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception:
        return error_interno('Error al guardar el visto bueno')


@api_roles_permitidos(['recepcion'])
def api_guardar_entrega(request, orden_id):
    """
    POST: Registra la entrega final del equipo y la encuesta.
    CONTROL DE ACCESO LOCAL: Exclusivo para Mesón de Recepción y Administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        datos = leer_json(request)

        try:
            nota = int(datos.get('nota', 5))
        except (TypeError, ValueError):
            nota = 0
        if not 1 <= nota <= 5:
            return JsonResponse({'error': 'La nota de satisfacción debe estar entre 1 y 5.'}, status=400)
        comentario = texto_seguro(datos.get('comentario'))
        retirado_tercero = datos.get('retiradoPorTercero') is True
        nombre_tercero = texto_seguro(datos.get('nombreTercero'), MAX_NOMBRE)
        rut_tercero = texto_seguro(datos.get('rutTercero'), 20)
        if retirado_tercero:
            if not nombre_tercero or not validar_rut(rut_tercero):
                return JsonResponse({
                    'error': 'Si retira un tercero debe indicar su nombre y un RUT válido.'
                }, status=400)
            rut_tercero = formatear_rut(rut_tercero)
        else:
            nombre_tercero, rut_tercero = '', ''

        EvaluacionSatisfaccion.objects.update_or_create(
            orden=orden,
            defaults={
                'nota': nota,
                'comentario': comentario,
                'retirado_por_tercero': retirado_tercero,
                'nombre_tercero': nombre_tercero,
                'rut_tercero': rut_tercero,
                'fecha_evaluacion': timezone.now()
            }
        )

        orden.estado = 'Entregado Conforme'
        orden.fecha_cierre = timezone.now()
        orden.save()

        registro.info('Entrega registrada: orden=%s por=%s tercero=%s', orden.id, usuario, retirado_tercero)
        return JsonResponse({
            'mensaje': 'Entrega final registrada.',
            'orden': dic_orden(orden, usuario)
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception:
        return error_interno('Error al registrar la entrega')


# ==============================================================================
# ENDPOINT DE MÉTRICAS Y ESTADÍSTICAS
# ==============================================================================

@api_roles_permitidos(['docente'])
def api_obtener_metricas(request):
    """GET: Retorna contadores calculados desde SQLite."""
    total = OrdenServicio.objects.count()
    preinscritos = OrdenServicio.objects.filter(estado='Preinscrito').count()
    recepcionados = OrdenServicio.objects.filter(estado='Recepcionado').count()
    en_taller = OrdenServicio.objects.filter(estado__in=['En Taller', 'Pausado']).count()
    listos = OrdenServicio.objects.filter(estado='Listo para Entrega').count()
    entregados = OrdenServicio.objects.filter(estado='Entregado Conforme').count()
    custodia = OrdenServicio.objects.filter(estado='En Custodia').count()

    encuestas = EvaluacionSatisfaccion.objects.all()
    if encuestas.exists():
        suma_notas = sum([e.nota for e in encuestas])
        promedio_satisfaccion = round(suma_notas / encuestas.count(), 1)
    else:
        promedio_satisfaccion = 5.0

    servicios = {
        # Una orden con varios servicios cuenta una vez en cada uno
        'Mantención Física': OrdenServicio.objects.filter(tipo_servicio__icontains='Mantención Física').count(),
        'Mantención Lógica': OrdenServicio.objects.filter(tipo_servicio__icontains='Mantención Lógica').count(),
        'Formateo': OrdenServicio.objects.filter(tipo_servicio__icontains='Formateo').count(),
    }

    return JsonResponse({
        'total': total,
        'preinscrito': preinscritos,
        'recepcionado': recepcionados,
        'enTaller': en_taller,
        'listo': listos,
        'entregado': entregados,
        'custodia': custodia,
        'promedioSatisfaccion': promedio_satisfaccion,
        'servicios': servicios
    })


# ==============================================================================
# ENDPOINT PARA RESTAURAR / POBLAR DATOS DE DEMOSTRACIÓN (Semilla Local)
# ==============================================================================

def sembrar_datos_demo():
    """
    Carga los datos de demostración en nuestra propia base de datos SQLite.
    Crea usuarios propios en la tabla Usuario y órdenes de prueba.
    Devuelve (ok, mensaje). La usan el comando 'poblar_datos' y el endpoint de administración.
    """
    try:
        with transaction.atomic():
            # 1. Creamos los usuarios propios de la Clínica en nuestra tabla Usuario
            usuarios_demo = [
                ('admin', 'admin123', 'admin', 'Administrador General', 'admin@inacap.cl'),
                ('docente', 'docente123', 'docente', 'Pablo Pesce Sánchez', 'ppesce@inacap.cl'),
                ('tecnico1', 'tecnico123', 'tecnico', 'Matías Garrido', 'mgarrido@alumnos.inacap.cl'),
                ('tecnico2', 'tecnico123', 'tecnico', 'Fernanda López', 'flopez@alumnos.inacap.cl'),
                ('recepcion', 'recepcion123', 'recepcion', 'Camila Contreras', 'ccontreras@inacap.cl'),
            ]

            for user_name, pass_word, rol, nom, email in usuarios_demo:
                u, _ = Usuario.objects.get_or_create(
                    nombre_usuario=user_name,
                    defaults={'nombre_completo': nom, 'correo': email, 'rol': rol}
                )
                u.fijar_contrasena(pass_word)
                u.nombre_completo = nom
                u.rol = rol
                u.save()

            # 2. Limpiamos datos previos de demostración
            EvaluacionSatisfaccion.objects.all().delete()
            VistoBuenoDocente.objects.all().delete()
            ObservacionOrden.objects.all().delete()
            ItemChecklist.objects.all().delete()
            OrdenServicio.objects.all().delete()
            Dispositivo.objects.all().delete()
            Propietario.objects.all().delete()

            # 3. Propietarios
            p1 = Propietario.objects.create(
                rut="18.452.910-6",
                nombre_completo="Carlos Vega Morales",
                telefono="+56 9 8452 1190",
                correo="carlos.vega@gmail.com",
                comuna="San Pedro de la Paz"
            )
            p2 = Propietario.objects.create(
                rut="12.784.331-7",
                nombre_completo="María Elena Fuentes",
                telefono="+56 9 7781 4420",
                correo="m.fuentes@inacap.cl",
                comuna="Concepción"
            )
            p3 = Propietario.objects.create(
                rut="20.119.458-K",
                nombre_completo="Rodrigo Parra Alarcón",
                telefono="+56 9 6321 0098",
                correo="rodrigo.parra20@inacapmail.cl",
                comuna="Coronel"
            )

            # 4. Dispositivos
            d1 = Dispositivo.objects.create(
                propietario=p1,
                tipo="Notebook",
                marca="Lenovo",
                modelo="IdeaPad 3 15ITL6",
                numero_serie="PF29XKL9",
                etiqueta_taller="CLI-PC-2026-0001",
                accesorios="Cargador original Lenovo 65W"
            )
            d2 = Dispositivo.objects.create(
                propietario=p1,
                tipo="Notebook",
                marca="HP",
                modelo="Pavilion x360",
                numero_serie="CND918491J",
                etiqueta_taller="CLI-PC-2026-0002",
                accesorios="Sin cargador"
            )
            d3 = Dispositivo.objects.create(
                propietario=p2,
                tipo="All-in-One",
                marca="HP",
                modelo="24-df0014la",
                numero_serie="8CC0210MQP",
                etiqueta_taller="CLI-PC-2026-0003",
                accesorios="Teclado y mouse USB HP"
            )
            d4 = Dispositivo.objects.create(
                propietario=p3,
                tipo="Notebook",
                marca="Asus",
                modelo="TUF Gaming FX505",
                numero_serie="L4NRCX0184",
                etiqueta_taller="CLI-PC-2026-0004",
                accesorios="Cargador de 150W Asus"
            )

            # 5. Órdenes con estados
            o1 = OrdenServicio.objects.create(
                dispositivo=d1,
                etiqueta_taller=d1.etiqueta_taller,
                estado="En Taller",
                tecnico_asignado="Matías Garrido",
                tipo_servicio="Mantención Física",
                falla_reportada="Calienta en exceso y ventilador suena fuerte",
                encendido_inicial=True,
                detalle_inspeccion_previa="Carcasa con rayones leves en tapa. Enciende normalmente a Windows."
            )
            for cod, desc in CATALOGO_CHECKLISTS['Mantención Física']:
                res = 'OK' if cod in ['F-01', 'F-02'] else 'PENDIENTE'
                ItemChecklist.objects.create(orden=o1, codigo_item=cod, descripcion=desc, resultado=res)
            ObservacionOrden.objects.create(
                orden=o1,
                autor="Matías Garrido",
                criticidad="Media",
                texto="Pasta térmica de fábrica totalmente cristalizada. Requiere limpieza con alcohol isopropílico."
            )

            o2 = OrdenServicio.objects.create(
                dispositivo=d2,
                etiqueta_taller=d2.etiqueta_taller,
                estado="Preinscrito",
                tipo_servicio="Mantención Lógica",
                falla_reportada="Sistema lento y mucha publicidad emergente"
            )
            for cod, desc in CATALOGO_CHECKLISTS['Mantención Lógica']:
                ItemChecklist.objects.create(orden=o2, codigo_item=cod, descripcion=desc, resultado='PENDIENTE')

            o3 = OrdenServicio.objects.create(
                dispositivo=d3,
                etiqueta_taller=d3.etiqueta_taller,
                estado="Listo para Entrega",
                tecnico_asignado="Fernanda López",
                tipo_servicio="Mantención Lógica",
                falla_reportada="Programas no abren y Windows desactualizado",
                encendido_inicial=True,
                detalle_inspeccion_previa="Pantalla sin rayas, equipo enciende correctamente.",
                llamada_realizada=True
            )
            for cod, desc in CATALOGO_CHECKLISTS['Mantención Lógica']:
                ItemChecklist.objects.create(orden=o3, codigo_item=cod, descripcion=desc, resultado='OK')
            ObservacionOrden.objects.create(
                orden=o3,
                autor="Fernanda López",
                criticidad="Baja",
                texto="Se eliminaron 14 GB de temporales y se desinstalaron 3 programas no deseados."
            )
            VistoBuenoDocente.objects.create(
                orden=o3,
                docente_nombre="Pablo Pesce Sánchez",
                comentario="Equipo verificado en banco de prueba. Rendimiento óptimo comprobado."
            )

            o4 = OrdenServicio.objects.create(
                dispositivo=d4,
                etiqueta_taller=d4.etiqueta_taller,
                estado="Entregado Conforme",
                tecnico_asignado="Ignacio Soto",
                tipo_servicio="Formateo",
                falla_reportada="Pantallazos azules tras actualización fallida",
                encendido_inicial=True,
                detalle_inspeccion_previa="Notebook con bisagra derecha suelta. Enciende hasta BIOS.",
                fecha_cierre=timezone.now(),
                llamada_realizada=True
            )
            for cod, desc in CATALOGO_CHECKLISTS['Formateo']:
                ItemChecklist.objects.create(orden=o4, codigo_item=cod, descripcion=desc, resultado='OK')
            ObservacionOrden.objects.create(
                orden=o4,
                autor="Ignacio Soto",
                criticidad="Baja",
                texto="Instalación de SO limpia completada sin incidencias."
            )
            VistoBuenoDocente.objects.create(
                orden=o4,
                docente_nombre="Pablo Pesce Sánchez",
                comentario="Certificado conforme."
            )
            EvaluacionSatisfaccion.objects.create(
                orden=o4,
                nota=5,
                comentario="Excelente servicio de los estudiantes, quedó impecable y muy rápido."
            )

            return True, 'Base de datos poblada exitosamente con usuarios locales y órdenes de prueba.'

    except Exception:
        registro.exception('Error al restaurar los datos de demostración')
        return False, 'No se pudieron restaurar los datos de demostración.'


@api_roles_permitidos(['admin'])
def api_restaurar_datos_demo(request):
    """
    POST: Restaura los datos de demostración.
    CONTROL DE ACCESO: solo el Administrador, y solo en modo desarrollo (borra todas las órdenes).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)
    if not settings.DEBUG:
        return JsonResponse({'error': 'Operación deshabilitada en modo producción.'}, status=403)

    ok, mensaje = sembrar_datos_demo()
    registro.warning('Datos de demostración restaurados por %s (ok=%s)', obtener_usuario_actual(request), ok)
    if ok:
        return JsonResponse({'mensaje': mensaje})
    return JsonResponse({'error': mensaje}, status=500)


def api_salud(request):
    """
    GET público y mínimo para monitorear la disponibilidad (continuidad operacional).
    No entrega datos del sistema: solo confirma si el servidor y la base de datos responden.
    """
    try:
        OrdenServicio.objects.exists()
    except Exception:
        registro.exception('Falla de disponibilidad de la base de datos')
        return JsonResponse({'estado': 'error'}, status=503)
    return JsonResponse({'estado': 'ok'})
