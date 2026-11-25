"""
Registro de modelos de Gestión en el Panel de Administración de Django.
"""

from django.contrib import admin
from .models import (
    Propietario, 
    Dispositivo, 
    OrdenServicio, 
    ItemChecklist, 
    ObservacionOrden, 
    VistoBuenoDocente, 
    EvaluacionSatisfaccion
)

class DispositivoEnLinea(admin.TabularInline):
    model = Dispositivo
    extra = 0

@admin.register(Propietario)
class PropietarioAdmin(admin.ModelAdmin):
    list_display = ('rut', 'nombre_completo', 'telefono', 'correo', 'comuna', 'fecha_registro')
    search_fields = ('rut', 'nombre_completo', 'correo')
    inlines = [DispositivoEnLinea]

@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = ('etiqueta_taller', 'tipo', 'marca', 'modelo', 'propietario')
    search_fields = ('etiqueta_taller', 'numero_serie', 'propietario__rut', 'propietario__nombre_completo')
    list_filter = ('tipo', 'marca')

class ItemChecklistEnLinea(admin.TabularInline):
    model = ItemChecklist
    extra = 0

class ObservacionEnLinea(admin.TabularInline):
    model = ObservacionOrden
    extra = 0

@admin.register(OrdenServicio)
class OrdenServicioAdmin(admin.ModelAdmin):
    list_display = ('id', 'etiqueta_taller', 'estado', 'tipo_servicio', 'tecnico_asignado', 'fecha_ingreso')
    list_filter = ('estado', 'tipo_servicio')
    search_fields = ('etiqueta_taller', 'dispositivo__propietario__rut', 'tecnico_asignado')
    inlines = [ItemChecklistEnLinea, ObservacionEnLinea]

admin.site.register(VistoBuenoDocente)
admin.site.register(EvaluacionSatisfaccion)
