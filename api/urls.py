"""
Enrutador de URLs para la API REST de la Clínica del PC.
Todas las rutas comienzan con /api/
"""

from django.urls import path
from . import views, views_admin

urlpatterns = [
    # Autenticación y control de sesión
    path('autenticacion/login/', views.api_iniciar_sesion, name='api_login'),
    path('autenticacion/logout/', views.api_cerrar_sesion, name='api_logout'),
    path('autenticacion/usuario-actual/', views.api_usuario_actual, name='api_usuario_actual'),

    # Propietarios y Dispositivos
    path('propietarios/', views.api_propietarios, name='api_propietarios'),
    path('dispositivos/', views.api_dispositivos, name='api_dispositivos'),

    # Órdenes de Servicio
    path('ordenes/', views.api_listar_o_crear_ordenes, name='api_ordenes'),
    path('ordenes/<int:orden_id>/', views.api_detalle_orden, name='api_detalle_orden'),
    path('ordenes/<int:orden_id>/estado/', views.api_cambiar_estado_orden, name='api_cambiar_estado'),
    path('ordenes/<int:orden_id>/checklists/', views.api_actualizar_checklist, name='api_actualizar_checklist'),
    path('ordenes/<int:orden_id>/observaciones/', views.api_agregar_observacion, name='api_agregar_observacion'),
    path('ordenes/<int:orden_id>/visto-bueno/', views.api_guardar_visto_bueno, name='api_visto_bueno'),
    path('ordenes/<int:orden_id>/entrega/', views.api_guardar_entrega, name='api_guardar_entrega'),

    # Métricas del Dashboard y Reportes
    path('metricas/', views.api_obtener_metricas, name='api_metricas'),

    # Administración (solo admin): carga masiva por CSV
    path('admin/plantilla-usuarios/', views_admin.api_plantilla_usuarios, name='api_plantilla_usuarios'),
    path('admin/plantilla-checklists/', views_admin.api_plantilla_checklists, name='api_plantilla_checklists'),
    path('admin/usuarios/', views_admin.api_listar_usuarios, name='api_admin_usuarios'),
    path('admin/usuarios/importar/', views_admin.api_importar_usuarios, name='api_importar_usuarios'),
    path('admin/checklists/', views_admin.api_listar_plantillas, name='api_admin_checklists'),
    path('admin/checklists/importar/', views_admin.api_importar_checklists, name='api_importar_checklists'),

    # Semilla de datos de prueba
    path('restaurar-datos/', views.api_restaurar_datos_demo, name='api_restaurar_datos'),
]
