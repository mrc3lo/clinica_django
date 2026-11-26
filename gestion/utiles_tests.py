"""Ayudas compartidas por las pruebas automatizadas: crear usuarios e iniciar sesión por la API."""

import json
from django.test import Client
from autenticacion.models import Usuario


def cliente_con_sesion(rol='admin', nombre_usuario=None, nombre_completo=None, clave='clave1234'):
    """Crea un usuario con ese rol, inicia sesión por la API y devuelve el Client ya autenticado."""
    nombre_usuario = nombre_usuario or f'{rol}_prueba'
    usuario = Usuario(nombre_usuario=nombre_usuario, nombre_completo=nombre_completo or f'Usuario {rol}', rol=rol)
    usuario.fijar_contrasena(clave)
    usuario.save()
    cliente = Client()
    respuesta = cliente.post('/api/autenticacion/login/', json.dumps({'usuario': nombre_usuario, 'clave': clave}),
                             content_type='application/json')
    assert respuesta.status_code == 200, respuesta.content
    return cliente
