"""
Pruebas de la búsqueda de titulares por nombre/RUT y del registro del número de serie en taller.
"""

import json
from django.test import TestCase, Client


class PruebasRecepcion(TestCase):
    def setUp(self):
        self.c = Client()
        self.ids = {}
        for rut, nombre in [('18.452.910-3', 'Carlos Vega Morales'),
                            ('12.784.331-K', 'María Elena Fuentes'),
                            ('20.119.458-2', 'Carla Vega Núñez')]:
            r = self.c.post('/api/ordenes/', json.dumps({
                'rut': rut, 'nombre': nombre, 'fallaReportada': 'x'}), content_type='application/json')
            self.ids[nombre] = r.json()['orden']['idOrden']

    def buscar(self, q):
        r = self.c.get('/api/ordenes/', {'q': q})
        return sorted(o['propietario']['nombre'] for o in r.json()['ordenes'])

    def test_01_busca_por_nombre_sin_importar_tildes_ni_mayusculas(self):
        self.assertEqual(self.buscar('maria elena'), ['María Elena Fuentes'])
        self.assertEqual(self.buscar('MARÍA'), ['María Elena Fuentes'])
        self.assertEqual(self.buscar('nunez'), ['Carla Vega Núñez'])

    def test_02_busca_por_parte_del_nombre_y_trae_varios_titulares(self):
        self.assertEqual(self.buscar('vega'), ['Carla Vega Núñez', 'Carlos Vega Morales'])
        self.assertEqual(self.buscar('carlos vega'), ['Carlos Vega Morales'])
        self.assertEqual(self.buscar('vega carlos'), ['Carlos Vega Morales'])  # el orden de las palabras no importa

    def test_03_busca_por_rut_completo_o_parcial_con_o_sin_formato(self):
        self.assertEqual(self.buscar('18.452.910-3'), ['Carlos Vega Morales'])
        self.assertEqual(self.buscar('18452910'), ['Carlos Vega Morales'])
        self.assertEqual(self.buscar('12.784'), ['María Elena Fuentes'])
        self.assertEqual(self.buscar('12784331k'), ['María Elena Fuentes'])

    def test_04_una_letra_sola_no_cuenta_como_rut(self):
        # "k" no tiene números: no debe coincidir con el RUT terminado en K
        self.assertEqual(self.buscar('k'), [])

    def test_05_sin_resultados(self):
        self.assertEqual(self.buscar('zzzz'), [])

    def test_06_tecnico_registra_numero_de_serie_y_recepcion_los_accesorios(self):
        id_orden = self.ids['Carlos Vega Morales']
        r = self.c.post(f'/api/ordenes/{id_orden}/', json.dumps({
            'numeroSerie': ' 5CD1234XYZ ', 'accesorios': 'Cargador y mouse'}), content_type='application/json')
        dispositivo = r.json()['orden']['dispositivo']
        self.assertEqual(dispositivo['numeroSerie'], '5CD1234XYZ')
        self.assertEqual(dispositivo['accesorios'], 'Cargador y mouse')
        # Se conserva al volver a consultar
        r = self.c.get(f'/api/ordenes/{id_orden}/')
        self.assertEqual(r.json()['orden']['dispositivo']['numeroSerie'], '5CD1234XYZ')

    def test_07_recepcionar_no_borra_el_numero_de_serie(self):
        id_orden = self.ids['Carlos Vega Morales']
        self.c.post(f'/api/ordenes/{id_orden}/', json.dumps({'numeroSerie': 'ABC123'}), content_type='application/json')
        r = self.c.post(f'/api/ordenes/{id_orden}/', json.dumps({
            'estado': 'Recepcionado', 'encendidoInicial': True}), content_type='application/json')
        self.assertEqual(r.json()['orden']['dispositivo']['numeroSerie'], 'ABC123')

    def test_08_no_se_puede_recepcionar_dos_veces(self):
        id_orden = self.ids['Carlos Vega Morales']
        datos = json.dumps({'estado': 'Recepcionado', 'encendidoInicial': True})
        r = self.c.post(f'/api/ordenes/{id_orden}/', datos, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['orden']['estado'], 'Recepcionado')

        # Segundo intento: se rechaza y no cambia nada (ni siquiera con el equipo ya en taller)
        self.c.post(f'/api/ordenes/{id_orden}/estado/', json.dumps({'estado': 'En Taller'}), content_type='application/json')
        r = self.c.post(f'/api/ordenes/{id_orden}/', datos, content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.c.get(f'/api/ordenes/{id_orden}/').json()['orden']['estado'], 'En Taller')

    def test_09_registro_express_solo_para_recepcion_y_admin(self):
        from autenticacion.models import Usuario
        for nombre, rol in [('rec_t', 'recepcion'), ('adm_t', 'admin'), ('tec_t', 'tecnico'), ('doc_t', 'docente')]:
            u = Usuario(nombre_usuario=nombre, nombre_completo=nombre, rol=rol)
            u.fijar_contrasena('clave1234')
            u.save()

        def entrar(nombre):
            c = Client()
            c.post('/api/autenticacion/login/', json.dumps({'usuario': nombre, 'clave': 'clave1234'}),
                   content_type='application/json')
            return c

        # Recepción y admin ven el formulario en modo express (200)
        for nombre in ['rec_t', 'adm_t']:
            r = entrar(nombre).get('/preinscripcion/')
            self.assertEqual(r.status_code, 200)
            self.assertIn('const MODO_EXPRESS = true', r.content.decode())
        # Técnico y docente siguen siendo redirigidos
        self.assertEqual(entrar('tec_t').get('/preinscripcion/').status_code, 302)
        self.assertEqual(entrar('doc_t').get('/preinscripcion/').status_code, 302)
        # El público general ve el formulario normal
        r = Client().get('/preinscripcion/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('const MODO_EXPRESS = false', r.content.decode())
