"""
Respaldo de la base de datos SQLite (continuidad de la operación).
Usa la API de respaldo de SQLite, que es segura aunque el sistema esté en uso, y conserva
solo los últimos N respaldos.

Uso:  python manage.py respaldar_bd
      python manage.py respaldar_bd --destino D:/respaldos --conservar 14
Restaurar: detener el servidor y copiar el archivo elegido sobre db.sqlite3.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Crea un respaldo fechado de la base de datos SQLite y elimina los más antiguos.'

    def add_arguments(self, parser):
        parser.add_argument('--destino', default=str(Path(settings.BASE_DIR) / 'respaldos'))
        parser.add_argument('--conservar', type=int, default=7, help='Cantidad de respaldos a mantener.')

    def handle(self, *args, **opciones):
        origen = Path(settings.DATABASES['default']['NAME'])
        if not origen.exists():
            raise CommandError(f'No existe la base de datos: {origen}')
        destino = Path(opciones['destino'])
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / f'clinica_{datetime.now():%Y%m%d_%H%M%S}.sqlite3'

        conexion_origen = sqlite3.connect(str(origen))
        conexion_destino = sqlite3.connect(str(archivo))
        try:
            conexion_origen.backup(conexion_destino)
        finally:
            conexion_destino.close()
            conexion_origen.close()

        antiguos = sorted(destino.glob('clinica_*.sqlite3'))[:-max(opciones['conservar'], 1)]
        for viejo in antiguos:
            viejo.unlink()
        self.stdout.write(self.style.SUCCESS(f'Respaldo creado: {archivo} (eliminados {len(antiguos)} antiguos)'))
