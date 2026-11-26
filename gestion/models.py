"""
Módulo de Gestión - Base de Datos de la Clínica del PC
Contiene las entidades del negocio: Propietarios, Dispositivos, Órdenes de Servicio,
Checklists técnicos, Observaciones de taller, V°B° docente y Encuesta de retiro.
"""

from django.db import models
from django.utils import timezone

# Estados por los que pasa un equipo en la Clínica del PC
ESTADOS_ORDEN = [
    ('Preinscrito', 'Pre-inscrito (QR)'),
    ('Recepcionado', 'Recepcionado Mesón'),
    ('En Taller', 'En Taller Técnico'),
    ('Pausado', 'Pausado / Traspaso'),
    ('Listo para Entrega', 'Listo para Entrega'),
    ('Entregado Conforme', 'Entregado Conforme'),
    ('En Custodia', 'En Custodia / Pañol'),
]

# Tipos de servicio que se ofrecen en la jornada
TIPOS_SERVICIO = [
    ('Mantención Física', 'Mantención Física (Limpieza de ventiladores, cambio de pasta térmica)'),
    ('Mantención Lógica', 'Mantención Lógica (Optimización, limpieza de malware, temporales)'),
    ('Formateo', 'Formateo e Instalación de Sistema Operativo'),
]

SERVICIOS_VALIDOS = [clave for clave, _ in TIPOS_SERVICIO]


def normalizar_servicios(valor):
    """
    Recibe una lista (['Formateo', 'Mantención Física']) o un texto separado por comas
    y devuelve la lista de servicios válidos, sin repetir y en el orden del catálogo.
    """
    if isinstance(valor, str):
        valor = [v.strip() for v in valor.split(',')]
    valor = set(valor or [])
    return [s for s in SERVICIOS_VALIDOS if s in valor]


# Tipos de dispositivos soportados
TIPOS_DISPOSITIVO = [
    ('Notebook', 'Notebook / Laptop'),
    ('Desktop', 'PC de Escritorio / Torre'),
    ('All-in-One', 'Todo en Uno (All-in-One)'),
    ('Mac', 'MacBook / Mac Mini / iMac'),
]

# Resultados posibles de cada punto de control en el checklist
RESULTADOS_CHECKLIST = [
    ('PENDIENTE', 'Pendiente de revisión'),
    ('OK', 'Revisión Conforme (OK)'),
    ('FALLA', 'Falla detectada'),
    ('NO_APLICA', 'No aplica para este caso'),
]


class Propietario(models.Model):
    """
    Representa a la persona titular del computador (estudiante, docente o vecino de la comunidad).
    """
    rut = models.CharField(max_length=20, unique=True, verbose_name="RUT del Titular")
    nombre_completo = models.CharField(max_length=150, verbose_name="Nombre Completo")
    telefono = models.CharField(max_length=30, verbose_name="Teléfono Celular")
    correo = models.EmailField(blank=True, default='', verbose_name="Correo Electrónico")
    comuna = models.CharField(max_length=100, default="San Pedro de la Paz", verbose_name="Comuna de Residencia")
    consentimiento_datos = models.BooleanField(
        default=True, 
        verbose_name="Consentimiento Informado (Ley 19.628)"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    def __str__(self):
        return f"{self.nombre_completo} ({self.rut})"

    def a_diccionario(self):
        """Convierte los datos del propietario a un diccionario Python para la API JSON"""
        return {
            'id': self.id,
            'rut': self.rut,
            'nombre': self.nombre_completo,
            'telefono': self.telefono,
            'email': self.correo,
            'comuna': self.comuna,
            'consentimiento': self.consentimiento_datos,
            'fechaRegistro': self.fecha_registro.strftime('%Y-%m-%d %H:%M') if self.fecha_registro else '',
        }


class Dispositivo(models.Model):
    """
    Representa el computador físico que ingresa al taller.
    """
    propietario = models.ForeignKey(
        Propietario, 
        on_delete=models.CASCADE, 
        related_name='dispositivos',
        verbose_name="Titular Propietario"
    )
    tipo = models.CharField(max_length=50, choices=TIPOS_DISPOSITIVO, default='Notebook', verbose_name="Tipo de Equipo")
    marca = models.CharField(max_length=50, verbose_name="Marca")
    modelo = models.CharField(max_length=100, verbose_name="Modelo")
    numero_serie = models.CharField(max_length=100, blank=True, default='', verbose_name="Número de Serie")
    etiqueta_taller = models.CharField(max_length=50, unique=True, verbose_name="Etiqueta / Código de Taller")
    accesorios = models.TextField(blank=True, default='Sin accesorios', verbose_name="Accesorios Recibidos")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    def __str__(self):
        return f"{self.tipo} {self.marca} {self.modelo} [{self.etiqueta_taller}]"

    def a_diccionario(self):
        """Convierte los datos del dispositivo a formato diccionario para la API JSON"""
        return {
            'idDispositivo': self.id,
            'rutPropietario': self.propietario.rut,
            'tipo': self.tipo,
            'marca': self.marca,
            'modelo': self.modelo,
            'numeroSerie': self.numero_serie,
            'etiquetaTaller': self.etiqueta_taller,
            'accesorios': self.accesorios,
        }


class OrdenServicio(models.Model):
    """
    Representa la ficha técnica y orden de trabajo activa en la clínica.
    Sigue el ciclo de vida de los 9 pasos del proceso.
    """
    dispositivo = models.ForeignKey(
        Dispositivo, 
        on_delete=models.CASCADE, 
        related_name='ordenes',
        verbose_name="Dispositivo"
    )
    etiqueta_taller = models.CharField(max_length=50, db_index=True, verbose_name="Etiqueta de Taller")
    estado = models.CharField(
        max_length=30, 
        choices=ESTADOS_ORDEN, 
        default='Preinscrito', 
        verbose_name="Estado Operativo"
    )
    # Una orden puede tener varios servicios: se guardan separados por coma
    # (ej: "Mantención Física, Formateo"). Use la propiedad 'servicios' para obtenerlos como lista.
    tipo_servicio = models.CharField(
        max_length=150,
        default='Mantención Física',
        verbose_name="Servicios Solicitados"
    )
    falla_reportada = models.TextField(verbose_name="Falla o Síntoma Reportado por el Titular")
    encendido_inicial = models.BooleanField(
        null=True, 
        blank=True, 
        verbose_name="Comprobación de Encendido (la realiza el técnico en taller)"
    )
    detalle_inspeccion_previa = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Inspección Visual de Carcasa / Golpes Preexistentes"
    )
    tecnico_asignado = models.CharField(
        max_length=120, 
        blank=True, 
        null=True, 
        verbose_name="Técnico Responsable Asignado"
    )
    fecha_ingreso = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora de Ingreso")
    fecha_cierre = models.DateTimeField(blank=True, null=True, verbose_name="Fecha de Cierre y Retiro")
    llamada_realizada = models.BooleanField(default=False, verbose_name="Aviso Telefónico de Retiro")

    def __str__(self):
        return f"Orden #{self.id} — {self.etiqueta_taller} ({self.estado})"

    @property
    def servicios(self):
        """Lista de servicios de la orden (ej: ['Mantención Física', 'Formateo'])."""
        return normalizar_servicios(self.tipo_servicio)

    def a_diccionario_completo(self):
        """
        Retorna la orden con todos sus detalles relacionados (titular, equipo, checklist,
        observaciones, visto bueno y encuesta) para que el frontend lo dibuje sin complicaciones.
        """
        # Obtenemos los checklists en un diccionario indexado por código (ej: F-01)
        checklists_dict = {}
        for item in self.items_checklist.order_by('id'):
            checklists_dict[item.codigo_item] = {
                'desc': item.descripcion,
                'res': item.resultado,
                'motivo': item.motivo_falla,
            }

        # Obtenemos la lista de observaciones
        lista_observaciones = []
        for obs in self.observaciones.all().order_by('fecha_registro'):
            lista_observaciones.append({
                'id': obs.id,
                'autor': obs.autor,
                'fecha': obs.fecha_registro.strftime('%Y-%m-%d %H:%M'),
                'criticidad': obs.criticidad,
                'texto': obs.texto,
            })

        # Obtenemos el V°B° docente si existe
        datos_visto_bueno = None
        if hasattr(self, 'visto_bueno'):
            vb = self.visto_bueno
            datos_visto_bueno = {
                'docente': vb.docente_nombre,
                'fecha': vb.fecha_aprobacion.strftime('%Y-%m-%d %H:%M'),
                'comentario': vb.comentario,
            }

        # Obtenemos la encuesta de satisfacción si existe
        datos_encuesta = None
        if hasattr(self, 'evaluacion'):
            ev = self.evaluacion
            datos_encuesta = {
                'nota': ev.nota,
                'comentario': ev.comentario,
                'retiradoPorTercero': ev.retirado_por_tercero,
                'nombreTercero': ev.nombre_tercero,
                'rutTercero': ev.rut_tercero,
                'fecha': ev.fecha_evaluacion.strftime('%Y-%m-%d %H:%M') if ev.fecha_evaluacion else '',
            }

        propietario = self.dispositivo.propietario

        return {
            'idOrden': self.id,
            'idDispositivo': self.dispositivo.id,
            'etiquetaTaller': self.etiqueta_taller,
            'estado': self.estado,
            'tecnicoAsignado': self.tecnico_asignado,
            'tipoServicio': ', '.join(self.servicios) or self.tipo_servicio,
            'servicios': self.servicios,
            'fallaReportada': self.falla_reportada,
            'encendidoInicial': self.encendido_inicial,
            'detalleInspeccionPrevia': self.detalle_inspeccion_previa,
            'fechaIngreso': self.fecha_ingreso.strftime('%Y-%m-%d %H:%M') if self.fecha_ingreso else '',
            'fechaCierre': self.fecha_cierre.strftime('%Y-%m-%d %H:%M') if self.fecha_cierre else None,
            'llamadaRealizada': self.llamada_realizada,
            'checklists': checklists_dict,
            'observaciones': lista_observaciones,
            'vistoBuenoDocente': datos_visto_bueno,
            # Alerta para el docente: un técnico reportó un posible contenido ilegal en el equipo
            'hallazgoLegal': any(o['texto'].startswith('[HALLAZGO LEGAL]') for o in lista_observaciones),
            'encuesta': datos_encuesta,
            # Datos aplanados útiles para las tablas y tarjetas del frontend
            'dispositivo': {
                'tipo': self.dispositivo.tipo,
                'marca': self.dispositivo.marca,
                'modelo': self.dispositivo.modelo,
                'numeroSerie': self.dispositivo.numero_serie,
                'accesorios': self.dispositivo.accesorios,
            },
            'propietario': {
                'rut': propietario.rut,
                'nombre': propietario.nombre_completo,
                'telefono': propietario.telefono,
                'email': propietario.correo,
                'comuna': propietario.comuna,
            }
        }


class ItemChecklist(models.Model):
    """
    Cada uno de los ítems de control de calidad y mantenimiento técnico.
    """
    orden = models.ForeignKey(
        OrdenServicio, 
        on_delete=models.CASCADE, 
        related_name='items_checklist'
    )
    codigo_item = models.CharField(max_length=20, verbose_name="Código (ej: F-01)")
    descripcion = models.CharField(max_length=250, verbose_name="Descripción de la Tarea")
    resultado = models.CharField(
        max_length=20, 
        choices=RESULTADOS_CHECKLIST, 
        default='PENDIENTE',
        verbose_name="Resultado del Control"
    )
    # Obligatorio cuando el resultado es FALLA: explica por qué falló el punto de control
    motivo_falla = models.TextField(blank=True, default='', verbose_name="Motivo de la falla")

    class Meta:
        unique_together = ('orden', 'codigo_item')

    def __str__(self):
        return f"{self.codigo_item} - {self.descripcion}: {self.resultado}"


class PlantillaChecklist(models.Model):
    """
    Ítem de la plantilla de checklist de un tipo de servicio.
    Se carga por CSV desde Administración y se copia a cada orden nueva.
    Si no hay plantilla cargada para un servicio, se usa el catálogo por defecto.
    """
    tipo_servicio = models.CharField(max_length=50, choices=TIPOS_SERVICIO, verbose_name="Tipo de Servicio")
    codigo = models.CharField(max_length=20, verbose_name="Código (ej: F-01)")
    descripcion = models.CharField(max_length=250, verbose_name="Descripción de la Tarea")
    posicion = models.PositiveIntegerField(default=0, verbose_name="Posición en la lista")

    class Meta:
        unique_together = ('tipo_servicio', 'codigo')
        ordering = ['tipo_servicio', 'posicion', 'id']

    def __str__(self):
        return f"{self.tipo_servicio}: {self.codigo} - {self.descripcion}"


class ObservacionOrden(models.Model):
    """
    Bitácora de notas técnicas o incidentes registrados por los estudiantes en el taller.
    """
    orden = models.ForeignKey(
        OrdenServicio, 
        on_delete=models.CASCADE, 
        related_name='observaciones'
    )
    autor = models.CharField(max_length=100, verbose_name="Autor de la Nota")
    criticidad = models.CharField(
        max_length=20, 
        choices=[('Baja', 'Baja'), ('Media', 'Media'), ('Alta', 'Alta')],
        default='Baja',
        verbose_name="Nivel de Criticidad"
    )
    texto = models.TextField(verbose_name="Detalle de la Observación")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora")

    def __str__(self):
        return f"Nota de {self.autor} ({self.criticidad})"


class VistoBuenoDocente(models.Model):
    """
    Certificación obligatoria de un profesor antes de autorizar la entrega del computador.
    """
    orden = models.OneToOneField(
        OrdenServicio, 
        on_delete=models.CASCADE, 
        related_name='visto_bueno'
    )
    docente_nombre = models.CharField(max_length=120, verbose_name="Nombre del Docente Supervisor")
    comentario = models.TextField(verbose_name="Observaciones de la Certificación")
    fecha_aprobacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Aprobación")

    def __str__(self):
        return f"V°B° por {self.docente_nombre}"


class EvaluacionSatisfaccion(models.Model):
    """
    Encuesta realizada al momento en que el titular retira su equipo.
    """
    orden = models.OneToOneField(
        OrdenServicio, 
        on_delete=models.CASCADE, 
        related_name='evaluacion'
    )
    nota = models.IntegerField(default=5, verbose_name="Calificación (1 a 5 estrellas)")
    comentario = models.TextField(blank=True, null=True, verbose_name="Opinión del Usuario")
    retirado_por_tercero = models.BooleanField(default=False, verbose_name="¿Fue retirado por un tercero?")
    nombre_tercero = models.CharField(max_length=120, blank=True, null=True, verbose_name="Nombre del Tercero")
    rut_tercero = models.CharField(max_length=20, blank=True, null=True, verbose_name="RUT del Tercero")
    fecha_evaluacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Encuesta")

    def __str__(self):
        return f"Nota: {self.nota}/5 ({self.orden.etiqueta_taller})"
