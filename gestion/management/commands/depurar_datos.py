"""
Política de retención de datos personales (Ley 19.628 y Ley 21.719: los datos solo se conservan
mientras son necesarios para la finalidad que los originó).

Anonimiza al titular cuando todas sus órdenes ya terminaron y pasó el plazo:
  - Entregado Conforme: 90 días desde el cierre (por defecto)
  - En Custodia: 180 días desde el ingreso (por defecto)
Se borran nombre, teléfono, correo y RUT (también los datos del tercero que retiró). Las órdenes,
checklists y encuestas se conservan sin datos personales para las métricas de la asignatura.

Uso:  python manage.py depurar_datos --simular
      python manage.py depurar_datos --dias-entregado 90 --dias-custodia 180
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from gestion.models import Propietario, OrdenServicio, EvaluacionSatisfaccion

registro = logging.getLogger('clinica')
PREFIJO_ANONIMO = 'ELIMINADO-'


def orden_vencida(orden, limite_entregado, limite_custodia):
    """True si la orden ya cumplió su plazo de retención."""
    if orden.estado == 'Entregado Conforme':
        return (orden.fecha_cierre or orden.fecha_ingreso) <= limite_entregado
    if orden.estado == 'En Custodia':
        return orden.fecha_ingreso <= limite_custodia
    return False  # una orden activa nunca se depura


def titulares_a_depurar(dias_entregado=90, dias_custodia=180, ahora=None):
    """Titulares cuyas órdenes (todas) están vencidas y que aún no fueron anonimizados."""
    ahora = ahora or timezone.now()
    limite_entregado = ahora - timedelta(days=dias_entregado)
    limite_custodia = ahora - timedelta(days=dias_custodia)
    resultado = []
    for propietario in Propietario.objects.exclude(rut__startswith=PREFIJO_ANONIMO):
        ordenes = OrdenServicio.objects.filter(dispositivo__propietario=propietario)
        if ordenes.exists() and all(orden_vencida(o, limite_entregado, limite_custodia) for o in ordenes):
            resultado.append(propietario)
    return resultado


def anonimizar(propietario):
    """Borra los datos personales del titular y de los terceros que retiraron sus equipos."""
    EvaluacionSatisfaccion.objects.filter(orden__dispositivo__propietario=propietario).update(
        nombre_tercero='', rut_tercero='', comentario='')
    propietario.rut = f'{PREFIJO_ANONIMO}{propietario.pk}'
    propietario.nombre_completo = 'Titular eliminado'
    propietario.telefono = ''
    propietario.correo = ''
    propietario.save()


class Command(BaseCommand):
    help = 'Anonimiza los datos personales de titulares cuyas órdenes superaron el plazo de retención.'

    def add_arguments(self, parser):
        parser.add_argument('--dias-entregado', type=int, default=90)
        parser.add_argument('--dias-custodia', type=int, default=180)
        parser.add_argument('--simular', action='store_true', help='Solo muestra cuántos titulares se depurarían.')

    def handle(self, *args, **opciones):
        candidatos = titulares_a_depurar(opciones['dias_entregado'], opciones['dias_custodia'])
        if opciones['simular']:
            self.stdout.write(f'Simulación: se anonimizarían {len(candidatos)} titular(es).')
            return
        for propietario in candidatos:
            anonimizar(propietario)
        registro.warning('Depuración de datos: %s titular(es) anonimizado(s)', len(candidatos))
        self.stdout.write(self.style.SUCCESS(f'Titulares anonimizados: {len(candidatos)}'))
