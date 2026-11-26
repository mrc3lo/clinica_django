"""
Pruebas de órdenes con más de un servicio.
"""

import json
from django.test import TestCase, Client
from gestion.utiles_tests import cliente_con_sesion


class PruebasMultiServicio(TestCase):
    def setUp(self):
        self.c = cliente_con_sesion("admin")

    def crear(self, **extra):
        datos = {'consentimiento': True, 'rut': '11.111.111-1', 'nombre': 'Cliente', 'fallaReportada': 'Lento'}
        datos.update(extra)
        r = self.c.post('/api/ordenes/', json.dumps(datos), content_type='application/json')
        self.assertEqual(r.status_code, 201)
        return r.json()['orden']

    def test_01_orden_con_dos_servicios_junta_los_checklists(self):
        orden = self.crear(servicios=['Formateo', 'Mantención Física'])
        # Se ordenan según el catálogo y se unen los checklists de ambos
        self.assertEqual(orden['servicios'], ['Mantención Física', 'Formateo'])
        self.assertEqual(orden['tipoServicio'], 'Mantención Física, Formateo')
        self.assertEqual(list(orden['checklists'].keys()),
                         ['F-01', 'F-02', 'F-03', 'F-04', 'F-05', 'R-01', 'R-02', 'R-03', 'R-04', 'R-05'])

    def test_02_sigue_funcionando_con_un_solo_servicio_en_texto(self):
        orden = self.crear(tipoServicio='Mantención Lógica')
        self.assertEqual(orden['servicios'], ['Mantención Lógica'])
        self.assertEqual(len(orden['checklists']), 5)

    def test_03_sin_servicios_validos_usa_el_por_defecto(self):
        orden = self.crear(servicios=['Cualquier cosa'])
        self.assertEqual(orden['servicios'], ['Mantención Física'])

    def test_04_cambiar_servicios_ajusta_checklist_sin_borrar_lo_revisado(self):
        orden = self.crear(servicios=['Mantención Física', 'Mantención Lógica'])
        id_orden = orden['idOrden']
        # Se revisa un ítem físico y uno lógico
        for codigo in ['F-01', 'L-01']:
            self.c.post(f'/api/ordenes/{id_orden}/checklists/', json.dumps({'codigo': codigo, 'resultado': 'OK'}),
                        content_type='application/json')
        # Se deja solo Formateo
        r = self.c.post(f'/api/ordenes/{id_orden}/', json.dumps({'servicios': ['Formateo']}), content_type='application/json')
        checklists = r.json()['orden']['checklists']
        self.assertEqual(r.json()['orden']['servicios'], ['Formateo'])
        # Quedan los revisados (F-01, L-01) y se agregan los de Formateo; los pendientes ajenos se van
        self.assertEqual(set(checklists.keys()), {'F-01', 'L-01', 'R-01', 'R-02', 'R-03', 'R-04', 'R-05'})
        self.assertEqual(checklists['F-01']['res'], 'OK')

    def test_05_filtro_y_metricas_cuentan_la_orden_en_cada_servicio(self):
        self.crear(servicios=['Mantención Física', 'Formateo'])
        self.crear(servicios=['Formateo'])
        r = self.c.get('/api/ordenes/?servicio=Formateo')
        self.assertEqual(len(r.json()['ordenes']), 2)
        r = self.c.get('/api/ordenes/?servicio=Mantención Física')
        self.assertEqual(len(r.json()['ordenes']), 1)
        m = self.c.get('/api/metricas/').json()
        self.assertEqual(m['servicios'], {'Mantención Física': 1, 'Mantención Lógica': 0, 'Formateo': 2})
