"""
Pruebas de continuidad y cumplimiento: respaldo de la base de datos, política de retención de datos
personales, protocolo ante contenido ilegal y endpoint de disponibilidad.
"""

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, Client
from django.utils import timezone

from gestion.models import Propietario, Dispositivo, OrdenServicio, EvaluacionSatisfaccion
from gestion.utiles_tests import cliente_con_sesion

JSON = 'application/json'


def crear_orden(rut, nombre, estado, dias_antiguedad, n):
    propietario = Propietario.objects.create(rut=rut, nombre_completo=nombre, telefono='+56 9 1234 5678', correo='a@b.cl')
    dispositivo = Dispositivo.objects.create(propietario=propietario, marca='HP', modelo='X', etiqueta_taller=f'CLI-PC-2026-9{n:03d}')
    fecha = timezone.now() - timedelta(days=dias_antiguedad)
    orden = OrdenServicio.objects.create(dispositivo=dispositivo, etiqueta_taller=dispositivo.etiqueta_taller,
                                         estado=estado, falla_reportada='x', fecha_cierre=fecha if estado == 'Entregado Conforme' else None)
    OrdenServicio.objects.filter(pk=orden.pk).update(fecha_ingreso=fecha)
    return propietario, orden


class PruebasRetencionDeDatos(TestCase):
    def test_01_anonimiza_solo_ordenes_vencidas(self):
        vencida, o1 = crear_orden('11.111.111-1', 'Titular Vencido', 'Entregado Conforme', 120, 1)
        reciente, _ = crear_orden('22.222.222-2', 'Titular Reciente', 'Entregado Conforme', 10, 2)
        activa, _ = crear_orden('33.333.333-3', 'Titular Activo', 'En Taller', 400, 3)
        custodia, _ = crear_orden('44.444.444-4', 'Titular Custodia', 'En Custodia', 200, 4)
        EvaluacionSatisfaccion.objects.create(orden=o1, nota=5, comentario='Muy bueno', retirado_por_tercero=True,
                                              nombre_tercero='Tercero', rut_tercero='5.555.555-5')
        call_command('depurar_datos', stdout=StringIO())
        for p in (vencida, reciente, activa, custodia):
            p.refresh_from_db()
        self.assertEqual(vencida.nombre_completo, 'Titular eliminado')
        self.assertEqual((vencida.telefono, vencida.correo), ('', ''))
        self.assertTrue(vencida.rut.startswith('ELIMINADO-'))
        self.assertEqual(custodia.nombre_completo, 'Titular eliminado')
        self.assertEqual(reciente.nombre_completo, 'Titular Reciente')   # aún dentro del plazo
        self.assertEqual(activa.nombre_completo, 'Titular Activo')       # orden activa: nunca se depura
        ev = EvaluacionSatisfaccion.objects.get(orden=o1)
        self.assertEqual((ev.nombre_tercero, ev.rut_tercero, ev.comentario), ('', '', ''))
        self.assertEqual(ev.nota, 5)  # la métrica se conserva sin datos personales

    def test_02_simulacion_no_modifica_nada(self):
        p, _ = crear_orden('11.111.111-1', 'Titular Vencido', 'Entregado Conforme', 120, 1)
        salida = StringIO()
        call_command('depurar_datos', '--simular', stdout=salida)
        p.refresh_from_db()
        self.assertEqual(p.nombre_completo, 'Titular Vencido')
        self.assertIn('1 titular', salida.getvalue())

    def test_03_titular_con_una_orden_activa_no_se_depura(self):
        p, _ = crear_orden('11.111.111-1', 'Titular Mixto', 'Entregado Conforme', 120, 1)
        dispositivo = Dispositivo.objects.create(propietario=p, marca='Dell', modelo='Y', etiqueta_taller='CLI-PC-2026-9999')
        OrdenServicio.objects.create(dispositivo=dispositivo, etiqueta_taller='CLI-PC-2026-9999', estado='En Taller', falla_reportada='x')
        call_command('depurar_datos', stdout=StringIO())
        p.refresh_from_db()
        self.assertEqual(p.nombre_completo, 'Titular Mixto')


class PruebasRespaldoYDisponibilidad(TestCase):
    def test_04_respaldo_crea_copia_valida_y_rota_los_antiguos(self):
        carpeta = tempfile.mkdtemp()
        try:
            base = os.path.join(carpeta, 'origen.sqlite3')
            con = sqlite3.connect(base)
            con.execute('create table t (x integer)')
            con.execute('insert into t values (42)')
            con.commit()
            con.close()
            destino = os.path.join(carpeta, 'resp')
            os.makedirs(destino)
            for nombre in ('clinica_20200101_000000.sqlite3', 'clinica_20200102_000000.sqlite3'):
                open(os.path.join(destino, nombre), 'w').close()
            with self.settings(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': base}}):
                call_command('respaldar_bd', '--destino', destino, '--conservar', '2', stdout=StringIO())
            archivos = sorted(os.listdir(destino))
            self.assertEqual(len(archivos), 2)  # se conservan los 2 más nuevos
            copia = sqlite3.connect(os.path.join(destino, archivos[-1]))
            self.assertEqual(copia.execute('select x from t').fetchone()[0], 42)
            copia.close()
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)

    def test_05_endpoint_de_salud_es_publico_y_no_revela_datos(self):
        r = Client().get('/api/salud/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'estado': 'ok'})


class PruebasHallazgoLegal(TestCase):
    def test_06_hallazgo_pausa_la_orden_alerta_al_docente_y_queda_en_bitacora(self):
        publico = Client()
        r = publico.post('/api/ordenes/', json.dumps({'consentimiento': True, 'rut': '11.111.111-1', 'nombre': 'Cliente',
                                                      'fallaReportada': 'x'}), content_type=JSON)
        id_orden = r.json()['orden']['idOrden']
        cliente_con_sesion('recepcion', 'rec1').post(f'/api/ordenes/{id_orden}/', json.dumps({'estado': 'Recepcionado'}), content_type=JSON)
        tecnico = cliente_con_sesion('tecnico', 'tec1', 'Ana Técnica')
        tecnico.post(f'/api/ordenes/{id_orden}/estado/', json.dumps({'estado': 'En Taller'}), content_type=JSON)
        r = tecnico.post(f'/api/ordenes/{id_orden}/observaciones/',
                         json.dumps({'texto': 'Archivos que podrían ser ilegales', 'hallazgoLegal': True}), content_type=JSON)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['observacion']['criticidad'], 'Alta')
        docente = cliente_con_sesion('docente', 'doc1')
        orden = docente.get(f'/api/ordenes/{id_orden}/').json()['orden']
        self.assertEqual(orden['estado'], 'Pausado')
        self.assertTrue(orden['hallazgoLegal'])
        self.assertTrue(orden['observaciones'][-1]['texto'].startswith('[HALLAZGO LEGAL]'))

    def test_07_recepcion_no_puede_registrar_observaciones_ni_hallazgos(self):
        r = Client().post('/api/ordenes/', json.dumps({'consentimiento': True, 'rut': '11.111.111-1', 'nombre': 'Cliente',
                                                       'fallaReportada': 'x'}), content_type=JSON)
        id_orden = r.json()['orden']['idOrden']
        r = cliente_con_sesion('recepcion', 'rec2').post(f'/api/ordenes/{id_orden}/observaciones/',
                                                         json.dumps({'texto': 'x', 'hallazgoLegal': True}), content_type=JSON)
        self.assertEqual(r.status_code, 403)
