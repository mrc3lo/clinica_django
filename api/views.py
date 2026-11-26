"""
Módulo API REST - Endpoints JSON con Autenticación Local Propia
No depende de django.contrib.auth. Utiliza la tabla propia 'Usuario' en SQLite
y el manejo de sesiones estándar de Django (request.session).
"""

import json
import re
import unicodedata
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction

# Importamos nuestro modelo propio de Usuario y utilidades de sesión
from autenticacion.models import Usuario
from autenticacion.decoradores import obtener_usuario_actual, obtener_rol_usuario
from gestion.models import (
    Propietario, 
    Dispositivo, 
    OrdenServicio, 
    ItemChecklist, 
    ObservacionOrden, 
    VistoBuenoDocente, 
    EvaluacionSatisfaccion,
    PlantillaChecklist,
    normalizar_servicios
)

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


# ==============================================================================
# ENDPOINTS DE AUTENTICACIÓN LOCAL PROPIA
# ==============================================================================

@csrf_exempt
def api_iniciar_sesion(request):
    """
    POST: Valida credenciales contra nuestra tabla local 'Usuario' en SQLite.
    Guarda en request.session el ID y rol del usuario, sin usar django-admin.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido. Use POST.'}, status=405)

    try:
        datos = json.loads(request.body)
        nombre_usuario = datos.get('usuario', '').strip()
        clave = datos.get('clave', '').strip()

        # Buscamos en nuestra tabla propia de usuarios
        usuario = Usuario.objects.filter(nombre_usuario=nombre_usuario, activo=True).first()

        if usuario and usuario.verificar_contrasena(clave):
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
            return JsonResponse({
                'error': 'Usuario o contraseña incorrectos. Por favor verifique.'
            }, status=401)

    except Exception as error:
        return JsonResponse({'error': f'Error en el proceso de login: {str(error)}'}, status=500)


@csrf_exempt
def api_cerrar_sesion(request):
    """POST o GET: Limpia la sesión del usuario."""
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

@csrf_exempt
def api_propietarios(request):
    """GET y POST para la gestión de propietarios."""
    if request.method == 'GET':
        rut_buscar = request.GET.get('rut', '').strip()
        if rut_buscar:
            propietarios = Propietario.objects.filter(rut__icontains=rut_buscar)
        else:
            propietarios = Propietario.objects.all().order_by('-fecha_registro')

        return JsonResponse({'propietarios': [p.a_diccionario() for p in propietarios]})

    elif request.method == 'POST':
        try:
            datos = json.loads(request.body)
            rut = datos.get('rut', '').strip()
            nombre = datos.get('nombre', '').strip()
            telefono = datos.get('telefono', '').strip()
            email = datos.get('email', '').strip()
            comuna = datos.get('comuna', 'San Pedro de la Paz').strip()
            consentimiento = datos.get('consentimiento', True)

            if not rut or not nombre:
                return JsonResponse({'error': 'El RUT y el Nombre son obligatorios'}, status=400)

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
        except Exception as error:
            return JsonResponse({'error': f'Error al registrar propietario: {str(error)}'}, status=500)

    return JsonResponse({'error': 'Método no soportado'}, status=405)


def api_dispositivos(request):
    """GET: Lista dispositivos en la base de datos."""
    rut = request.GET.get('rut', '').strip()
    if rut:
        dispositivos = Dispositivo.objects.filter(propietario__rut__icontains=rut)
    else:
        dispositivos = Dispositivo.objects.all().order_by('-id')

    return JsonResponse({'dispositivos': [d.a_diccionario() for d in dispositivos]})


# ==============================================================================
# ENDPOINTS DE ÓRDENES DE SERVICIO
# ==============================================================================

@csrf_exempt
def api_listar_o_crear_ordenes(request):
    """
    GET: Lista órdenes con filtros opcionales.
    POST: Crea nueva orden (preinscripción o mesón).
    """
    if request.method == 'GET':
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
        usuario = obtener_usuario_actual(request)
        ordenes = [o for o in ordenes if not orden_oculta_para_tecnico(usuario, o)]

        return JsonResponse({'ordenes': [orden.a_diccionario_completo() for orden in ordenes]})

    elif request.method == 'POST':
        try:
            with transaction.atomic():
                datos = json.loads(request.body)

                rut = datos.get('rut', '').strip()
                nombre = datos.get('nombre', '').strip()
                telefono = datos.get('telefono', '').strip()
                email = datos.get('email', '').strip()
                comuna = datos.get('comuna', 'San Pedro de la Paz').strip()
                consentimiento = datos.get('consentimiento', True)

                if not rut or not nombre:
                    return JsonResponse({'error': 'El RUT y el Nombre del titular son obligatorios.'}, status=400)

                propietario, _ = Propietario.objects.update_or_create(
                    rut=rut,
                    defaults={
                        'nombre_completo': nombre,
                        'telefono': telefono,
                        'correo': email,
                        'comuna': comuna,
                        'consentimiento_datos': consentimiento
                    }
                )

                total_equipos = Dispositivo.objects.count() + 1
                etiqueta = f"CLI-PC-2026-{total_equipos:04d}"

                tipo = datos.get('tipo', 'Notebook')
                marca = datos.get('marca', 'Genérico')
                modelo = datos.get('modelo', 'Estándar')
                numero_serie = datos.get('numeroSerie', '')
                accesorios = datos.get('accesorios', 'Sin accesorios')

                dispositivo = Dispositivo.objects.create(
                    propietario=propietario,
                    tipo=tipo,
                    marca=marca,
                    modelo=modelo,
                    numero_serie=numero_serie,
                    etiqueta_taller=etiqueta,
                    accesorios=accesorios
                )

                estado_inicial = datos.get('estado', 'Preinscrito')
                servicios = servicios_desde_datos(datos)
                tipo_servicio = ', '.join(servicios)
                falla = datos.get('fallaReportada', 'Mantención preventiva solicitada')
                encendido = datos.get('encendidoInicial', None)
                inspeccion = datos.get('detalleInspeccionPrevia', '')
                tecnico = datos.get('tecnicoAsignado', None)

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
                    'orden': orden.a_diccionario_completo()
                }, status=201)

        except Exception as error:
            return JsonResponse({'error': f'Error al registrar la orden: {str(error)}'}, status=500)

    return JsonResponse({'error': 'Método no soportado'}, status=405)


@csrf_exempt
def api_detalle_orden(request, orden_id):
    """GET o PUT/POST: Consulta o actualiza campos de la orden."""
    try:
        orden = OrdenServicio.objects.select_related('dispositivo', 'dispositivo__propietario').get(id=orden_id)
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': f'No existe una orden con ID {orden_id}'}, status=404)

    if orden_oculta_para_tecnico(obtener_usuario_actual(request), orden):
        return respuesta_orden_ajena()

    if request.method == 'GET':
        return JsonResponse({'orden': orden.a_diccionario_completo()})

    elif request.method in ['PUT', 'POST']:
        try:
            datos = json.loads(request.body)
            # Una orden solo se recepciona una vez: debe venir desde "Preinscrito"
            if datos.get('estado') == 'Recepcionado' and orden.estado != 'Preinscrito':
                return JsonResponse({
                    'error': f'Esta orden ya fue recepcionada (estado actual: {orden.estado}).'
                }, status=409)
            if 'estado' in datos:
                orden.estado = datos['estado']
            if 'tecnicoAsignado' in datos:
                orden.tecnico_asignado = datos['tecnicoAsignado']
            if 'encendidoInicial' in datos:
                orden.encendido_inicial = datos['encendidoInicial']
            if 'detalleInspeccionPrevia' in datos:
                orden.detalle_inspeccion_previa = datos['detalleInspeccionPrevia']
            servicios_cambiaron = False
            if 'servicios' in datos or 'tipoServicio' in datos:
                nuevos = servicios_desde_datos(datos, por_defecto=orden.servicios)
                servicios_cambiaron = nuevos != orden.servicios
                orden.tipo_servicio = ', '.join(nuevos)
            if 'fallaReportada' in datos:
                orden.falla_reportada = datos['fallaReportada']
            if 'llamadaRealizada' in datos:
                orden.llamada_realizada = datos['llamadaRealizada']

            # Datos del equipo: el número de serie lo registra el técnico en taller;
            # los accesorios los registra recepción al recibir el equipo.
            dispositivo = orden.dispositivo
            if 'numeroSerie' in datos:
                dispositivo.numero_serie = str(datos['numeroSerie']).strip()[:100]
            if 'accesorios' in datos:
                dispositivo.accesorios = str(datos['accesorios']).strip() or 'Sin accesorios'
            if 'numeroSerie' in datos or 'accesorios' in datos:
                dispositivo.save()

            orden.save()
            if servicios_cambiaron:
                sincronizar_checklist(orden)
            return JsonResponse({
                'mensaje': 'Orden actualizada correctamente',
                'orden': orden.a_diccionario_completo()
            })
        except Exception as error:
            return JsonResponse({'error': f'Error al actualizar orden: {str(error)}'}, status=500)

    return JsonResponse({'error': 'Método no soportado'}, status=405)


@csrf_exempt
def api_cambiar_estado_orden(request, orden_id):
    """POST: Cambia el estado de una orden en el flujo operativo."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        usuario = obtener_usuario_actual(request)
        if orden_oculta_para_tecnico(usuario, orden):
            return respuesta_orden_ajena()
        datos = json.loads(request.body)
        nuevo_estado = datos.get('estado')

        if not nuevo_estado:
            return JsonResponse({'error': 'Debe especificar el nuevo estado'}, status=400)

        orden.estado = nuevo_estado
        if nuevo_estado == 'Entregado Conforme' and not orden.fecha_cierre:
            orden.fecha_cierre = timezone.now()

        if 'tecnicoAsignado' in datos:
            orden.tecnico_asignado = datos['tecnicoAsignado']
        # Si lo hace un técnico, el equipo queda siempre a su nombre (no se puede asignar a otro)
        if usuario and usuario.rol == 'tecnico':
            orden.tecnico_asignado = usuario.nombre_completo

        orden.save()

        return JsonResponse({
            'mensaje': f'Estado cambiado a "{nuevo_estado}"',
            'orden': orden.a_diccionario_completo()
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)


@csrf_exempt
def api_actualizar_checklist(request, orden_id):
    """POST: Actualiza el resultado de un ítem de checklist."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)
    if usuario and usuario.rol not in ['tecnico', 'docente', 'admin']:
        return JsonResponse({'error': 'Acceso denegado: rol no autorizado para modificar checklist.'}, status=403)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        if orden_oculta_para_tecnico(usuario, orden):
            return respuesta_orden_ajena()
        datos = json.loads(request.body)
        codigo = datos.get('codigo')
        resultado = datos.get('resultado', 'OK')
        descripcion = datos.get('desc', '')
        motivo = str(datos.get('motivo', '') or '').strip()

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
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)


@csrf_exempt
def api_agregar_observacion(request, orden_id):
    """POST: Registra anotación en la bitácora técnica de la orden."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        if orden_oculta_para_tecnico(obtener_usuario_actual(request), orden):
            return respuesta_orden_ajena()
        datos = json.loads(request.body)
        texto = datos.get('texto', '').strip()
        autor = datos.get('autor', '').strip() or 'Técnico de Turno'
        criticidad = datos.get('criticidad', 'Baja')

        if not texto:
            return JsonResponse({'error': 'El texto de la observación no puede estar vacío'}, status=400)

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
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)


@csrf_exempt
def api_guardar_visto_bueno(request, orden_id):
    """
    POST: Certificación y firma de Visto Bueno.
    CONTROL DE ACCESO LOCAL: Exclusivo para Docente Supervisor y Administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)
    if usuario and usuario.rol not in ['docente', 'admin']:
        return JsonResponse({
            'error': 'Acceso denegado: El Visto Bueno requiere rol Docente Supervisor.'
        }, status=403)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        datos = json.loads(request.body)
        docente = datos.get('docente', '').strip() or (usuario.nombre_completo if usuario else 'Docente Supervisor')
        comentario = datos.get('comentario', '').strip() or 'Certificado en banco de prueba.'

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

        return JsonResponse({
            'mensaje': 'Visto Bueno Docente registrado. Orden lista para entrega.',
            'orden': orden.a_diccionario_completo()
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)


@csrf_exempt
def api_guardar_entrega(request, orden_id):
    """
    POST: Registra la entrega final del equipo y la encuesta.
    CONTROL DE ACCESO LOCAL: Exclusivo para Mesón de Recepción y Administrador.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

    usuario = obtener_usuario_actual(request)
    if usuario and usuario.rol not in ['recepcion', 'admin']:
        return JsonResponse({
            'error': 'Acceso denegado: La entrega y encuesta solo puede ser realizada por el Mesón de Recepción.'
        }, status=403)

    try:
        orden = OrdenServicio.objects.get(id=orden_id)
        datos = json.loads(request.body)

        nota = int(datos.get('nota', 5))
        comentario = datos.get('comentario', '')
        retirado_tercero = datos.get('retiradoPorTercero', False)
        nombre_tercero = datos.get('nombreTercero', '')
        rut_tercero = datos.get('rutTercero', '')

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

        return JsonResponse({
            'mensaje': 'Entrega final registrada.',
            'orden': orden.a_diccionario_completo()
        })
    except OrdenServicio.DoesNotExist:
        return JsonResponse({'error': 'Orden no encontrada'}, status=404)
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=500)


# ==============================================================================
# ENDPOINT DE MÉTRICAS Y ESTADÍSTICAS
# ==============================================================================

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

@csrf_exempt
def api_restaurar_datos_demo(request):
    """
    POST: Carga los datos de demostración en nuestra propia base de datos SQLite.
    Crea usuarios propios en la tabla Usuario y órdenes de prueba.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Use POST'}, status=405)

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
                rut="18.452.910-3",
                nombre_completo="Carlos Vega Morales",
                telefono="+56 9 8452 1190",
                correo="carlos.vega@gmail.com",
                comuna="San Pedro de la Paz"
            )
            p2 = Propietario.objects.create(
                rut="12.784.331-K",
                nombre_completo="María Elena Fuentes",
                telefono="+56 9 7781 4420",
                correo="m.fuentes@inacap.cl",
                comuna="Concepción"
            )
            p3 = Propietario.objects.create(
                rut="20.119.458-2",
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

            return JsonResponse({'mensaje': 'Base de datos poblada exitosamente con usuarios locales y órdenes de prueba.'})

    except Exception as error:
        return JsonResponse({'error': f'Error al restaurar: {str(error)}'}, status=500)
