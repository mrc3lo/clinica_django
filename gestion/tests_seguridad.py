"""
Pruebas de seguridad (OWASP Top 10): control de acceso, CSRF, validación de entradas,
privacidad del RUT, fuerza bruta en el login y manejo de contraseñas.
"""

import json
from django.core.cache import cache
from django.test import TestCase, Client
from autenticacion.models import Usuario
from gestion.models import Propietario
from gestion.utiles_tests import cliente_con_sesion
from gestion.validadores import validar_rut, enmascarar_rut

JSON = 'application/json'


def datos_orden(**extra):
    datos = {'consentimiento': True, 'rut': '11.111.111-1', 'nombre': 'Cliente Seguro',
             'telefono': '+56 9 1234 5678', 'fallaReportada': 'No enciende'}
    datos.update(extra)
    return json.dumps(datos)


class PruebasSeguridad(TestCase):
    def setUp(self):
        cache.clear()

    # --- A01: control de acceso -------------------------------------------------
    def test_01_api_con_datos_personales_exige_sesion(self):
        anonimo = Client()
        for ruta in ['/api/ordenes/', '/api/propietarios/', '/api/dispositivos/', '/api/metricas/',
                     '/api/ordenes/1/', '/api/admin/usuarios/']:
            self.assertEqual(anonimo.get(ruta).status_code, 401, ruta)

    def test_02_acciones_sensibles_exigen_sesion_y_rol(self):
        anonimo = Client()
        for ruta in ['/api/ordenes/1/visto-bueno/', '/api/ordenes/1/entrega/', '/api/ordenes/1/checklists/',
                     '/api/ordenes/1/estado/', '/api/restaurar-datos/']:
            self.assertEqual(anonimo.post(ruta, '{}', content_type=JSON).status_code, 401, ruta)
        tecnico = cliente_con_sesion('tecnico')
        self.assertEqual(tecnico.post('/api/ordenes/1/visto-bueno/', '{}', content_type=JSON).status_code, 403)
        self.assertEqual(tecnico.post('/api/ordenes/1/entrega/', '{}', content_type=JSON).status_code, 403)
        self.assertEqual(tecnico.post('/api/restaurar-datos/', '{}', content_type=JSON).status_code, 403)
        self.assertEqual(tecnico.get('/api/metricas/').status_code, 403)

    def test_03_preinscripcion_publica_no_puede_forzar_estado_ni_datos_de_taller(self):
        r = Client().post('/api/ordenes/', datos_orden(estado='Listo para Entrega', encendidoInicial=True,
                                                       tecnicoAsignado='Otro', detalleInspeccionPrevia='x'),
                          content_type=JSON)
        self.assertEqual(r.status_code, 201)
        orden = r.json()['orden']
        self.assertEqual(orden['estado'], 'Preinscrito')
        self.assertIsNone(orden['tecnicoAsignado'])
        self.assertIsNone(orden['encendidoInicial'])

    def test_04_publico_no_sobrescribe_datos_de_un_titular_existente(self):
        Propietario.objects.create(rut='11.111.111-1', nombre_completo='Nombre Original', telefono='+56 9 1111 1111')
        Client().post('/api/ordenes/', datos_orden(nombre='Atacante'), content_type=JSON)
        self.assertEqual(Propietario.objects.get(rut='11.111.111-1').nombre_completo, 'Nombre Original')

    # --- A03: validación de entradas --------------------------------------------
    def test_05_rut_invalido_telefono_y_correo_se_rechazan_en_el_servidor(self):
        c = Client()
        self.assertEqual(c.post('/api/ordenes/', datos_orden(rut='11.111.111-9'), content_type=JSON).status_code, 400)
        self.assertEqual(c.post('/api/ordenes/', datos_orden(telefono='abc'), content_type=JSON).status_code, 400)
        self.assertEqual(c.post('/api/ordenes/', datos_orden(email='no-es-correo'), content_type=JSON).status_code, 400)

    def test_06_sin_consentimiento_no_se_registran_datos(self):
        r = Client().post('/api/ordenes/', datos_orden(consentimiento=False), content_type=JSON)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Propietario.objects.exists())

    def test_07_estado_y_nota_invalidos_se_rechazan(self):
        admin = cliente_con_sesion('admin')
        id_orden = admin.post('/api/ordenes/', datos_orden(), content_type=JSON).json()['orden']['idOrden']
        r = admin.post(f'/api/ordenes/{id_orden}/estado/', json.dumps({'estado': 'Inventado'}), content_type=JSON)
        self.assertEqual(r.status_code, 400)
        recepcion = cliente_con_sesion('recepcion')
        r = recepcion.post(f'/api/ordenes/{id_orden}/entrega/', json.dumps({'nota': 99}), content_type=JSON)
        self.assertEqual(r.status_code, 400)

    def test_08_json_malformado_no_provoca_error_interno(self):
        r = Client().post('/api/autenticacion/login/', 'esto no es json', content_type=JSON)
        self.assertEqual(r.status_code, 401)

    def test_09_validador_de_rut_modulo_11(self):
        self.assertTrue(validar_rut('11.111.111-1'))
        self.assertTrue(validar_rut('20119458K'))
        self.assertFalse(validar_rut('11.111.111-2'))
        self.assertFalse(validar_rut("1'; DROP TABLE--"))
        self.assertEqual(enmascarar_rut('12.345.678-5'), 'XX.XXX.XXX-5')

    # --- Privacidad (Ley 19.628) --------------------------------------------------
    def test_10_el_tecnico_recibe_el_rut_enmascarado_desde_el_servidor(self):
        Client().post('/api/ordenes/', datos_orden(), content_type=JSON)
        tecnico = cliente_con_sesion('tecnico')
        ordenes = tecnico.get('/api/ordenes/').json()['ordenes']
        self.assertEqual(len(ordenes), 0)  # Preinscrito: aún no está disponible para el técnico
        admin = cliente_con_sesion('admin')
        id_orden = admin.get('/api/ordenes/').json()['ordenes'][0]['idOrden']
        admin.post(f'/api/ordenes/{id_orden}/', json.dumps({'estado': 'Recepcionado'}), content_type=JSON)
        propietario = tecnico.get('/api/ordenes/').json()['ordenes'][0]['propietario']
        self.assertEqual(propietario['rut'], 'XX.XXX.XXX-1')
        self.assertNotIn('11.111.111', json.dumps(tecnico.get(f'/api/ordenes/{id_orden}/').json()))

    # --- A07: autenticación -------------------------------------------------------
    def test_11_login_se_bloquea_tras_cinco_intentos_fallidos(self):
        u = Usuario(nombre_usuario='victima', nombre_completo='Víctima', rol='tecnico')
        u.fijar_contrasena('clave1234')
        u.save()
        c = Client()
        for _ in range(5):
            r = c.post('/api/autenticacion/login/', json.dumps({'usuario': 'victima', 'clave': 'mala'}), content_type=JSON)
            self.assertEqual(r.status_code, 401)
        r = c.post('/api/autenticacion/login/', json.dumps({'usuario': 'victima', 'clave': 'clave1234'}), content_type=JSON)
        self.assertEqual(r.status_code, 429)

    def test_12_la_contrasena_solo_se_compara_contra_su_hash(self):
        u = Usuario(nombre_usuario='texto', nombre_completo='Texto Plano', rol='tecnico', contrasena='clave1234')
        u.save()  # contraseña guardada SIN hash (caso inseguro)
        self.assertFalse(u.verificar_contrasena('clave1234'))
        u.fijar_contrasena('clave1234')
        self.assertTrue(u.verificar_contrasena('clave1234'))
        self.assertNotEqual(u.contrasena, 'clave1234')

    # --- A01/A05: CSRF ------------------------------------------------------------
    def test_13_las_peticiones_que_modifican_datos_exigen_token_csrf(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post('/api/ordenes/', datos_orden(), content_type=JSON)
        self.assertEqual(r.status_code, 403)
        c.get('/login/')  # el portal entrega la cookie con el token
        token = c.cookies['csrftoken'].value
        r = c.post('/api/ordenes/', datos_orden(), content_type=JSON, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 201)

    def test_14_cerrar_sesion_solo_por_post(self):
        self.assertEqual(Client().get('/api/autenticacion/logout/').status_code, 405)

    def test_15_cookie_de_sesion_httponly_y_samesite(self):
        u = Usuario(nombre_usuario='cookie', nombre_completo='Cookie', rol='tecnico')
        u.fijar_contrasena('clave1234')
        u.save()
        r = Client().post('/api/autenticacion/login/', json.dumps({'usuario': 'cookie', 'clave': 'clave1234'}), content_type=JSON)
        morsel = r.cookies['sessionid']
        self.assertTrue(morsel['httponly'])
        self.assertEqual(morsel['samesite'], 'Lax')
