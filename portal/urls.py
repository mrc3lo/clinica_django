"""
Enrutador de URLs para las páginas web del Portal.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.vista_dashboard, name='portal_dashboard'),
    path('login/', views.vista_login, name='portal_login'),
    path('preinscripcion/', views.vista_preinscripcion, name='portal_preinscripcion'),
    path('recepcion/', views.vista_recepcion, name='portal_recepcion'),
    path('taller/', views.vista_taller, name='portal_taller'),
    path('control-calidad/', views.vista_calidad, name='portal_calidad'),
    path('entrega/', views.vista_entrega, name='portal_entrega'),
    path('metricas/', views.vista_metricas, name='portal_metricas'),
    path('estudiantes/', views.vista_estudiantes, name='portal_estudiantes'),
    path('administracion/', views.vista_administracion, name='portal_administracion'),
]
