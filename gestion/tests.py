"""
Pruebas Unitarias y de Integración - Clínica del PC INACAP
Valida la API REST local, el Modelo propio de Usuario y el Control de Acceso por Roles (RBAC).
Todo implementado con la tabla local 'Usuario' en SQLite sin usar django.contrib.auth.
"""

import json
from django.test import TestCase, Client
from autenticacion.models import Usuario
from gestion.models import Propietario, Dispositivo, OrdenServicio

class PruebasControlAccesoYRoles(TestCase):
    def setUp(self):
        """Creamos 4 usuarios de prueba en nuestra tabla propia 'Usuario'"""
        self.cliente = Client()

        # 1. Administrador General
        self.u_admin = Usuario.objects.create(
            nombre_usuario='admin_test',
            nombre_completo='Admin Pruebas',
            correo='admin@inacap.cl',
            rol='admin'
        )
        self.u_admin.fijar_contrasena('admin123')
        self.u_admin.save()

        # 2. Docente Supervisor
        self.u_docente = Usuario.objects.create(
            nombre_usuario='docente_test',
            nombre_completo='Profesor Pablo Pesce',
            correo='ppesce@inacap.cl',
            rol='docente'
        )
        self.u_docente.fijar_contrasena('docente123')
        self.u_docente.save()

        # 3. Alumno Técnico de Taller
        self.u_tecnico = Usuario.objects.create(
            nombre_usuario='tecnico_test',
            nombre_completo='Matías Garrido',
            correo='mgarrido@alumnos.inacap.cl',
            rol='tecnico'
        )
        self.u_tecnico.fijar_contrasena('tecnico123')
        self.u_tecnico.save()

        # 4. Mesón de Recepción
        self.u_recepcion = Usuario.objects.create(
            nombre_usuario='recepcion_test',
            nombre_completo='Camila Contreras',
            correo='ccontreras@inacap.cl',
            rol='recepcion'
        )
        self.u_recepcion.fijar_contrasena('recepcion123')
        self.u_recepcion.save()

    def iniciar_sesion(self, usuario):
        """Método auxiliar para simular la sesión activa en el cliente de prueba"""
        sesion = self.cliente.session
        sesion['usuario_id'] = usuario.id
        sesion['usuario_rol'] = usuario.rol
        sesion['usuario_nombre'] = usuario.nombre_completo
        sesion.save()

    def test_01_administrador_acceso_total(self):
        """El administrador debe poder acceder a todos los módulos sin excepción (200 OK)"""
        self.iniciar_sesion(self.u_admin)
        vistas = ['/', '/recepcion/', '/taller/', '/control-calidad/', '/entrega/', '/metricas/']
        for ruta in vistas:
            resp = self.cliente.get(ruta)
            self.assertEqual(resp.status_code, 200, f"Fallo de acceso para admin en {ruta}")

    def test_02_tecnico_acceso_restringido(self):
        """
        El técnico solo trabaja en Taller.
        Si intenta acceder al Panel o Pre-inscripción, se le redirige a /taller/.
        A otros módulos protegidos recibe 403 (Acceso Denegado).
        """
        self.iniciar_sesion(self.u_tecnico)

        # Acceso permitido:
        self.assertEqual(self.cliente.get('/taller/').status_code, 200)

        # Si intenta entrar al Panel principal, se le redirige a su taller:
        resp_panel = self.cliente.get('/')
        self.assertEqual(resp_panel.status_code, 302)
        self.assertEqual(resp_panel.url, '/taller/')

        # Si intenta entrar a pre-inscripción pública, se le redirige a su taller:
        resp_pre = self.cliente.get('/preinscripcion/')
        self.assertEqual(resp_pre.status_code, 302)
        self.assertEqual(resp_pre.url, '/taller/')

        # Acceso denegado a otros módulos (403):
        self.assertEqual(self.cliente.get('/recepcion/').status_code, 403)
        self.assertEqual(self.cliente.get('/control-calidad/').status_code, 403)
        self.assertEqual(self.cliente.get('/entrega/').status_code, 403)
        self.assertEqual(self.cliente.get('/metricas/').status_code, 403)

    def test_03_recepcion_acceso_restringido(self):
        """
        Recepción solo opera en Mesón y Entrega.
        El Panel principal está restringido: al entrar a '/', se le redirige a '/recepcion/'.
        A otros módulos no autorizados recibe 403.
        """
        self.iniciar_sesion(self.u_recepcion)

        # Acceso permitido:
        self.assertEqual(self.cliente.get('/recepcion/').status_code, 200)
        self.assertEqual(self.cliente.get('/entrega/').status_code, 200)

        # El Panel principal redirige al mesón:
        resp_panel = self.cliente.get('/')
        self.assertEqual(resp_panel.status_code, 302)
        self.assertEqual(resp_panel.url, '/recepcion/')

        # Acceso denegado (403):
        self.assertEqual(self.cliente.get('/taller/').status_code, 403)
        self.assertEqual(self.cliente.get('/control-calidad/').status_code, 403)
        self.assertEqual(self.cliente.get('/metricas/').status_code, 403)

    def test_04_docente_acceso_restringido(self):
        """
        El Docente Supervisor accede al Panel Principal, Calidad, Métricas y Taller.
        No tiene por qué acceder al Mesón de Entrada ni a Entrega de Equipos.
        """
        self.iniciar_sesion(self.u_docente)

        # Acceso permitido (incluye el Panel Principal /):
        self.assertEqual(self.cliente.get('/').status_code, 200)
        self.assertEqual(self.cliente.get('/control-calidad/').status_code, 200)
        self.assertEqual(self.cliente.get('/metricas/').status_code, 200)
        self.assertEqual(self.cliente.get('/taller/').status_code, 200)

        # Acceso denegado (403):
        self.assertEqual(self.cliente.get('/recepcion/').status_code, 403)
        self.assertEqual(self.cliente.get('/entrega/').status_code, 403)

    def test_05_api_seguridad_visto_bueno(self):
        """Un técnico NO puede firmar el visto bueno en la API; el docente SÍ"""
        prop = Propietario.objects.create(rut="12.345.678-9", nombre_completo="Cliente Test", telefono="123")
        disp = Dispositivo.objects.create(propietario=prop, tipo="Notebook", marca="HP", modelo="15", etiqueta_taller="CLI-PC-2026-0099")
        orden = OrdenServicio.objects.create(dispositivo=disp, etiqueta_taller="CLI-PC-2026-0099", estado="En Taller")

        # 1. Técnico intenta firmar V°B° -> Debe ser rechazado con 403
        self.iniciar_sesion(self.u_tecnico)
        resp_tec = self.cliente.post(
            f'/api/ordenes/{orden.id}/visto-bueno/',
            data=json.dumps({'docente': 'Intruso', 'comentario': 'hack'}),
            content_type='application/json'
        )
        self.assertEqual(resp_tec.status_code, 403)

        # 2. Docente firma V°B° -> Debe ser aceptado con 200
        self.iniciar_sesion(self.u_docente)
        resp_doc = self.cliente.post(
            f'/api/ordenes/{orden.id}/visto-bueno/',
            data=json.dumps({'docente': 'Pablo Pesce', 'comentario': 'Aprobado formalmente'}),
            content_type='application/json'
        )
        self.assertEqual(resp_doc.status_code, 200)

    def test_06_login_api_local(self):
        """Prueba el endpoint de login local propio en SQLite"""
        # Credenciales correctas
        resp_ok = self.cliente.post(
            '/api/autenticacion/login/',
            data=json.dumps({'usuario': 'docente_test', 'clave': 'docente123'}),
            content_type='application/json'
        )
        self.assertEqual(resp_ok.status_code, 200)
        datos = resp_ok.json()
        self.assertEqual(datos['usuario']['rol'], 'docente')
        self.assertEqual(datos['url_destino'], '/')

        # Credenciales incorrectas
        resp_err = self.cliente.post(
            '/api/autenticacion/login/',
            data=json.dumps({'usuario': 'docente_test', 'clave': 'clave_erronea'}),
            content_type='application/json'
        )
        self.assertEqual(resp_err.status_code, 401)
