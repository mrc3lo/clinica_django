"""
Pruebas del perfil técnico: visibilidad de equipos, motivo de falla en el checklist,
verificación de encendido y redirección en vez de pantalla de módulo restringido.
"""

import json
from django.test import TestCase, Client

from autenticacion.models import Usuario
from gestion.models import OrdenServicio


def crear_usuario(nombre_usuario, nombre, rol):
    u = Usuario(nombre_usuario=nombre_usuario, nombre_completo=nombre, rol=rol)
    u.fijar_contrasena('clave1234')
    u.save()
    return u


def sesion(nombre_usuario):
    c = Client()
    r = c.post('/api/autenticacion/login/', json.dumps({'usuario': nombre_usuario, 'clave': 'clave1234'}),
               content_type='application/json')
    assert r.status_code == 200
    return c


class PruebasPerfilTecnico(TestCase):
    def setUp(self):
        crear_usuario('tec_a', 'Ana Técnica', 'tecnico')
        crear_usuario('tec_b', 'Beto Técnico', 'tecnico')
        crear_usuario('doc', 'Docente Uno', 'docente')
        crear_usuario('rec', 'Recepción Uno', 'recepcion')

        # Una orden por cada situación
        publico = Client()
        self.ordenes = {}
        for clave, rut in [('espera', '11.111.111-1'), ('de_ana', '22.222.222-2'),
                           ('de_beto', '33.333.333-3'), ('preinscrita', '44.444.444-4')]:
            r = publico.post('/api/ordenes/', json.dumps({
                'consentimiento': True, 'rut': rut, 'nombre': f'Cliente {clave}', 'fallaReportada': 'x'}), content_type='application/json')
            self.ordenes[clave] = r.json()['orden']['idOrden']
        OrdenServicio.objects.filter(id=self.ordenes['espera']).update(estado='Recepcionado')
        OrdenServicio.objects.filter(id=self.ordenes['de_ana']).update(estado='En Taller', tecnico_asignado='Ana Técnica')
        OrdenServicio.objects.filter(id=self.ordenes['de_beto']).update(estado='Pausado', tecnico_asignado='Beto Técnico')

    def ids_visibles(self, cliente):
        return {o['idOrden'] for o in cliente.get('/api/ordenes/').json()['ordenes']}

    def test_01_tecnico_solo_ve_en_espera_y_los_suyos(self):
        visibles = self.ids_visibles(sesion('tec_a'))
        self.assertEqual(visibles, {self.ordenes['espera'], self.ordenes['de_ana']})

    def test_02_otro_tecnico_ve_distinto(self):
        visibles = self.ids_visibles(sesion('tec_b'))
        self.assertEqual(visibles, {self.ordenes['espera'], self.ordenes['de_beto']})

    def test_03_docente_y_recepcion_siguen_viendo_todo(self):
        self.assertEqual(len(self.ids_visibles(sesion('doc'))), 4)
        self.assertEqual(len(self.ids_visibles(sesion('rec'))), 4)

    def test_04_tecnico_no_puede_abrir_ni_modificar_equipos_ajenos(self):
        ana = sesion('tec_a')
        ajena = self.ordenes['de_beto']
        self.assertEqual(ana.get(f'/api/ordenes/{ajena}/').status_code, 403)
        self.assertEqual(ana.post(f'/api/ordenes/{ajena}/', json.dumps({'numeroSerie': 'X'}),
                                  content_type='application/json').status_code, 403)
        self.assertEqual(ana.post(f'/api/ordenes/{ajena}/estado/', json.dumps({'estado': 'En Taller'}),
                                  content_type='application/json').status_code, 403)
        self.assertEqual(ana.post(f'/api/ordenes/{ajena}/checklists/', json.dumps({'codigo': 'F-01', 'resultado': 'OK'}),
                                  content_type='application/json').status_code, 403)
        # Tampoco puede ver una orden que aún no pasó por recepción
        self.assertEqual(ana.get(f"/api/ordenes/{self.ordenes['preinscrita']}/").status_code, 403)

    def test_05_tomar_un_equipo_en_espera_lo_deja_a_su_nombre(self):
        ana = sesion('tec_a')
        id_orden = self.ordenes['espera']
        # Aunque intente asignarlo a otra persona, queda a su propio nombre
        r = ana.post(f'/api/ordenes/{id_orden}/estado/',
                     json.dumps({'estado': 'En Taller', 'tecnicoAsignado': 'Beto Técnico'}),
                     content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['orden']['tecnicoAsignado'], 'Ana Técnica')
        # Ya no está en espera: Beto deja de verlo
        self.assertNotIn(id_orden, self.ids_visibles(sesion('tec_b')))

    def test_06_falla_exige_motivo(self):
        ana = sesion('tec_a')
        url = f"/api/ordenes/{self.ordenes['de_ana']}/checklists/"
        r = ana.post(url, json.dumps({'codigo': 'F-01', 'resultado': 'FALLA'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('por qué', r.json()['error'])
        r = ana.post(url, json.dumps({'codigo': 'F-01', 'resultado': 'FALLA', 'motivo': '   '}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = ana.post(url, json.dumps({'codigo': 'F-01', 'resultado': 'FALLA', 'motivo': 'Ventilador trabado'}),
                     content_type='application/json')
        self.assertEqual(r.status_code, 200)
        detalle = ana.get(f"/api/ordenes/{self.ordenes['de_ana']}/").json()['orden']
        self.assertEqual(detalle['checklists']['F-01'], {
            'desc': detalle['checklists']['F-01']['desc'], 'res': 'FALLA', 'motivo': 'Ventilador trabado'})

    def test_07_cambiar_a_ok_borra_el_motivo(self):
        ana = sesion('tec_a')
        url = f"/api/ordenes/{self.ordenes['de_ana']}/checklists/"
        ana.post(url, json.dumps({'codigo': 'F-02', 'resultado': 'FALLA', 'motivo': 'Roto'}), content_type='application/json')
        ana.post(url, json.dumps({'codigo': 'F-02', 'resultado': 'OK'}), content_type='application/json')
        detalle = ana.get(f"/api/ordenes/{self.ordenes['de_ana']}/").json()['orden']
        self.assertEqual(detalle['checklists']['F-02']['res'], 'OK')
        self.assertEqual(detalle['checklists']['F-02']['motivo'], '')

    def test_08_resultado_invalido_se_rechaza(self):
        r = sesion('tec_a').post(f"/api/ordenes/{self.ordenes['de_ana']}/checklists/",
                                 json.dumps({'codigo': 'F-01', 'resultado': 'TAL_VEZ'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_09_tecnico_verifica_el_encendido(self):
        ana = sesion('tec_a')
        id_orden = self.ordenes['de_ana']
        self.assertIsNone(ana.get(f'/api/ordenes/{id_orden}/').json()['orden']['encendidoInicial'])
        r = ana.post(f'/api/ordenes/{id_orden}/', json.dumps({'encendidoInicial': False}), content_type='application/json')
        self.assertIs(r.json()['orden']['encendidoInicial'], False)

    def test_10_seccion_no_autorizada_devuelve_al_area_de_trabajo(self):
        tecnico = sesion('tec_a')
        for ruta in ['/recepcion/', '/control-calidad/', '/entrega/', '/metricas/', '/administracion/']:
            r = tecnico.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertEqual(r.url, '/taller/?aviso=sin-acceso', ruta)
        # Recepción vuelve al mesón y docente a su panel
        self.assertEqual(sesion('rec').get('/taller/').url, '/recepcion/?aviso=sin-acceso')
        self.assertEqual(sesion('doc').get('/entrega/').url, '/?aviso=sin-acceso')

    def test_11_pantalla_equipos_por_estudiante_solo_docente_y_admin(self):
        crear_usuario('adm', 'Admin Uno', 'admin')
        self.assertEqual(sesion('doc').get('/estudiantes/').status_code, 200)
        self.assertEqual(sesion('adm').get('/estudiantes/').status_code, 200)
        for quien, destino in [('tec_a', '/taller/'), ('rec', '/recepcion/')]:
            r = sesion(quien).get('/estudiantes/')
            self.assertEqual(r.status_code, 302)
            self.assertEqual(r.url, f'{destino}?aviso=sin-acceso')

    def test_12_docente_ve_los_equipos_de_todos_los_estudiantes(self):
        ordenes = sesion('doc').get('/api/ordenes/').json()['ordenes']
        por_estudiante = {}
        for o in ordenes:
            if o['tecnicoAsignado']:
                por_estudiante.setdefault(o['tecnicoAsignado'], []).append(o['idOrden'])
        self.assertEqual(por_estudiante, {'Ana Técnica': [self.ordenes['de_ana']], 'Beto Técnico': [self.ordenes['de_beto']]})
