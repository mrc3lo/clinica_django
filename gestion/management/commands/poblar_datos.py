"""
Comando de Django para poblar la base de datos local con datos de prueba iniciales.
Uso en terminal: python manage.py poblar_datos
"""

from django.core.management.base import BaseCommand
from django.test import RequestFactory
from api.views import api_restaurar_datos_demo

class Command(BaseCommand):
    help = 'Puebla la base de datos SQLite con los datos de prueba del prototipo de la Clínica del PC'

    def handle(self, *args, **options):
        # Creamos una petición simulada POST para reutilizar la función de restauración
        factory = RequestFactory()
        request = factory.post('/api/restaurar-datos/')
        respuesta = api_restaurar_datos_demo(request)
        
        if respuesta.status_code == 200:
            self.stdout.write(self.style.SUCCESS('✅ ¡Base de datos poblada exitosamente con usuarios, equipos y órdenes de prueba!'))
            self.stdout.write(self.style.SUCCESS('Credenciales creadas:'))
            self.stdout.write('  - Administrador: usuario: admin  | clave: admin123')
            self.stdout.write('  - Docente:       usuario: docente | clave: docente123')
            self.stdout.write('  - Técnico:       usuario: tecnico1 | clave: tecnico123')
            self.stdout.write('  - Recepción:     usuario: recepcion | clave: recepcion123')
        else:
            self.stdout.write(self.style.ERROR(f'❌ Error al poblar datos: {respuesta.content.decode()}'))
