"""
Validaciones del lado del servidor (OWASP A03: Inyección / validación de entradas).
Nunca se confía solo en la validación del navegador: el servidor revisa de nuevo todo lo que recibe.
"""

import re

# Largos máximos permitidos para los textos que llegan por la API
MAX_NOMBRE = 150
MAX_TEXTO_CORTO = 100
MAX_TEXTO_LARGO = 1000


def calcular_dv(numero):
    """Calcula el dígito verificador de un RUT chileno con el algoritmo módulo 11."""
    suma, multiplicador = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return '0'
    if resto == 10:
        return 'K'
    return str(resto)


def validar_rut(rut):
    """True si el RUT tiene formato correcto y su dígito verificador coincide (módulo 11)."""
    limpio = re.sub(r'[.\-\s]', '', str(rut or '')).upper()
    if not re.fullmatch(r'\d{7,8}[0-9K]', limpio):
        return False
    return calcular_dv(limpio[:-1]) == limpio[-1]


def formatear_rut(rut):
    """Devuelve el RUT con puntos y guion (12.345.678-5). Se asume que ya es válido."""
    limpio = re.sub(r'[.\-\s]', '', str(rut or '')).upper()
    cuerpo, dv = limpio[:-1], limpio[-1:]
    cuerpo = f'{int(cuerpo):,}'.replace(',', '.') if cuerpo.isdigit() else cuerpo
    return f'{cuerpo}-{dv}'


def enmascarar_rut(rut):
    """
    Oculta el cuerpo del RUT y deja solo el dígito verificador (XX.XXX.XXX-5).
    Se usa con el perfil técnico: no necesita el RUT completo para reparar un equipo (Ley 19.628).
    """
    partes = str(rut or '').split('-')
    dv = partes[1] if len(partes) == 2 else 'X'
    return f'XX.XXX.XXX-{dv}'


def validar_telefono(telefono):
    """Acepta vacío o un teléfono de 8 a 15 dígitos, con +, espacios y guiones opcionales."""
    if not telefono:
        return True
    return bool(re.fullmatch(r'\+?[\d\s\-]{8,20}', telefono)) and 8 <= len(re.sub(r'\D', '', telefono)) <= 15


def validar_correo(correo):
    """Acepta vacío o un correo con formato básico válido."""
    if not correo:
        return True
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', correo)) and len(correo) <= 254


def texto_seguro(valor, maximo=MAX_TEXTO_LARGO):
    """Convierte a texto, quita espacios sobrantes y limita el largo."""
    return str(valor if valor is not None else '').strip()[:maximo]
