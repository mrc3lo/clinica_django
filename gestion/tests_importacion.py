"""
Pruebas de la carga masiva por CSV (usuarios y checklists) y de la pantalla de Administración.
"""

import json
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client

from autenticacion.models import Usuario
from gestion.models import PlantillaChecklist, OrdenServicio


def csv_subido(texto, nombre='datos.csv', codificacion='utf-8-sig'):
    return SimpleUploadedFile(nombre, texto.encode(codificacion), content_type='text/csv')


class PruebasImportacionCSV(TestCase):
    def setUp(self):
        self.cliente = Client()
        for nombre, rol in [('admin_t', 'admin'), ('docente_t', 'docente')]:
            u = Usuario(nombre_usuario=nombre, nombre_completo=nombre, rol=rol)
            u.fijar_contrasena('clave1234')
            u.save()

    def entrar(self, usuario):
        r = self.cliente.post('/api/autenticacion/login/',
                              json.dumps({'usuario': usuario, 'clave': 'clave1234'}),
                              content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def importar(self, url, texto, confirmar):
        return self.cliente.post(url, {'archivo': csv_subido(texto), 'confirmar': '1' if confirmar else '0'})

    # ---------------- Usuarios ----------------
    def test_01_usuarios_vista_previa_no_guarda(self):
        self.entrar('admin_t')
        csv = 'nombre_usuario;nombre_completo;correo;rol\nmgomez;Marta Gómez;m@inacap.cl;docente\n'
        r = self.importar('/api/admin/usuarios/importar/', csv, False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['resumen']['nuevo'], 1)
        self.assertFalse(Usuario.objects.filter(nombre_usuario='mgomez').exists())

    def test_02_usuarios_confirmar_crea_omite_y_reporta_errores(self):
        self.entrar('admin_t')
        csv = (
            'nombre_usuario,nombre_completo,correo,rol,telefono,contrasena\n'
            'mgomez,Marta Gómez,m@inacap.cl,docente,,\n'          # nuevo, clave generada
            'jperez,Juan Pérez,,Alumno,,miclave99\n'              # nuevo, rol alias, clave dada
            'docente_t,Ya Existe,,docente,,\n'                    # omitido
            'xx,Usuario corto,,tecnico,,\n'                       # error: usuario muy corto
            'hacker,Intento Admin,,admin,,\n'                     # error: rol no permitido
            'mgomez,Repetido,,tecnico,,\n'                        # error: repetido en archivo
        )
        r = self.importar('/api/admin/usuarios/importar/', csv, True)
        datos = r.json()
        self.assertEqual(datos['resumen'], {'nuevo': 2, 'omitido': 1, 'error': 3})

        marta = Usuario.objects.get(nombre_usuario='mgomez')
        self.assertEqual(marta.rol, 'docente')
        clave_generada = next(f['clave_inicial'] for f in datos['filas'] if f['nombre_usuario'] == 'mgomez' and f.get('clave_inicial'))
        self.assertEqual(len(clave_generada), 8)
        self.assertTrue(marta.verificar_contrasena(clave_generada))
        self.assertNotEqual(marta.contrasena, clave_generada)  # se guarda con hash

        juan = Usuario.objects.get(nombre_usuario='jperez')
        self.assertEqual(juan.rol, 'tecnico')
        self.assertTrue(juan.verificar_contrasena('miclave99'))
        self.assertFalse(Usuario.objects.filter(nombre_usuario='hacker').exists())

    def test_03_usuarios_csv_con_columnas_faltantes(self):
        self.entrar('admin_t')
        r = self.importar('/api/admin/usuarios/importar/', 'usuario,nombre\nabc,Alguien\n', False)
        self.assertEqual(r.status_code, 400)
        self.assertIn('rol', r.json()['error'])

    def test_04_usuarios_acepta_latin1_y_alias_de_columnas(self):
        self.entrar('admin_t')
        texto = 'usuario;nombre;email;rol\nnuñez01;Ñandú Núñez;n@inacap.cl;técnico\n'
        r = self.cliente.post('/api/admin/usuarios/importar/',
                              {'archivo': csv_subido(texto, codificacion='latin-1'), 'confirmar': '1'})
        self.assertEqual(r.json()['resumen']['error'], 1)  # 'ñ' no es válido en el nombre de usuario
        texto = 'usuario;nombre;email;rol\nnunez01;Ñandú Núñez;n@inacap.cl;técnico\n'
        r = self.cliente.post('/api/admin/usuarios/importar/',
                              {'archivo': csv_subido(texto, codificacion='latin-1'), 'confirmar': '1'})
        self.assertEqual(r.json()['resumen']['nuevo'], 1)
        self.assertEqual(Usuario.objects.get(nombre_usuario='nunez01').nombre_completo, 'Ñandú Núñez')

    # ---------------- Checklists ----------------
    def test_05_checklists_reemplaza_solo_servicios_incluidos(self):
        self.entrar('admin_t')
        PlantillaChecklist.objects.create(tipo_servicio='Formateo', codigo='R-01', descripcion='Antiguo', posicion=1)
        csv = (
            'tipo_servicio;codigo;descripcion\n'
            'Mantención Física;F-01;Abrir equipo\n'
            'mantencion fisica;F-02;Limpiar\n'          # sin tildes y minúsculas: se acepta
            'Servicio Raro;X-01;No existe\n'            # error
        )
        r = self.importar('/api/admin/checklists/importar/', csv, True)
        self.assertEqual(r.json()['resumen'], {'nuevo': 2, 'omitido': 0, 'error': 1})
        codigos = list(PlantillaChecklist.objects.filter(tipo_servicio='Mantención Física').values_list('codigo', flat=True))
        self.assertEqual(codigos, ['F-01', 'F-02'])
        # Formateo no estaba en el CSV: se conserva
        self.assertTrue(PlantillaChecklist.objects.filter(tipo_servicio='Formateo', codigo='R-01').exists())

    def test_06_orden_nueva_usa_plantilla_csv(self):
        self.entrar('admin_t')
        csv = 'tipo_servicio;codigo;descripcion\nFormateo;Z-01;Paso uno\nFormateo;Z-02;Paso dos\n'
        self.importar('/api/admin/checklists/importar/', csv, True)
        r = self.cliente.post('/api/ordenes/', json.dumps({
            'consentimiento': True, 'rut': '11.111.111-1', 'nombre': 'Cliente Prueba', 'tipoServicio': 'Formateo',
            'fallaReportada': 'Lento'}), content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(list(r.json()['orden']['checklists'].keys()), ['Z-01', 'Z-02'])

    def test_07_orden_nueva_sin_plantilla_usa_catalogo_por_defecto(self):
        r = self.cliente.post('/api/ordenes/', json.dumps({
            'consentimiento': True, 'rut': '22.222.222-2', 'nombre': 'Otro Cliente', 'tipoServicio': 'Mantención Lógica',
            'fallaReportada': 'Lento'}), content_type='application/json')
        self.assertEqual(list(r.json()['orden']['checklists'].keys()), ['L-01', 'L-02', 'L-03', 'L-04', 'L-05'])

    def test_08_ordenes_existentes_no_cambian_al_cargar_plantilla(self):
        r = self.cliente.post('/api/ordenes/', json.dumps({
            'consentimiento': True, 'rut': '33.333.333-3', 'nombre': 'Cliente', 'tipoServicio': 'Formateo',
            'fallaReportada': 'x'}), content_type='application/json')
        id_orden = r.json()['orden']['idOrden']
        self.entrar('admin_t')
        self.importar('/api/admin/checklists/importar/', 'tipo_servicio;codigo;descripcion\nFormateo;Z-01;Nuevo\n', True)
        orden = OrdenServicio.objects.get(id=id_orden)
        self.assertEqual(orden.items_checklist.count(), 5)

    # ---------------- Acceso ----------------
    def test_09_solo_admin_accede_a_administracion(self):
        # Sin sesión: la página redirige al login y la API responde 401
        self.assertEqual(self.cliente.get('/administracion/').status_code, 302)
        self.assertEqual(self.cliente.get('/api/admin/usuarios/').status_code, 401)
        # Docente: la página lo devuelve a su panel y la API responde 403
        self.entrar('docente_t')
        r = self.cliente.get('/administracion/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('aviso=sin-acceso', r.url)
        self.assertEqual(self.cliente.get('/api/admin/usuarios/').status_code, 403)
        r = self.importar('/api/admin/usuarios/importar/', 'nombre_usuario,nombre_completo,rol\na1b,A,tecnico\n', True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Usuario.objects.filter(nombre_usuario='a1b').exists())

    def test_10_admin_ve_pagina_y_descarga_plantillas(self):
        self.entrar('admin_t')
        self.assertEqual(self.cliente.get('/administracion/').status_code, 200)
        r = self.cliente.get('/api/admin/plantilla-usuarios/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('nombre_usuario', r.content.decode('utf-8-sig'))
        r = self.cliente.get('/api/admin/plantilla-checklists/')
        contenido = r.content.decode('utf-8-sig')
        self.assertIn('F-01', contenido)  # precargada con el catálogo vigente
        self.assertIn('R-05', contenido)
