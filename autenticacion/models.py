"""
Módulo de Autenticación - Modelo de Usuario Propio
Implementación local sin depender del modelo estándar auth_user de Django.
Permite gestionar cuentas, roles, nombres y contraseñas directamente en nuestra BD SQLite.
"""

from django.db import models
from django.contrib.auth.hashers import make_password, check_password

# Roles definidos para la Clínica del PC
ROLES_USUARIO = [
    ('admin', 'Administrador General'),
    ('docente', 'Docente Supervisor'),
    ('recepcion', 'Mesón de Recepción y Atención'),
    ('tecnico', 'Estudiante Técnico de Taller'),
]

class Usuario(models.Model):
    """
    Tabla propia de usuarios en SQLite para el control de acceso del sistema.
    """
    nombre_usuario = models.CharField(
        max_length=50, 
        unique=True, 
        verbose_name="Nombre de Usuario"
    )
    contrasena = models.CharField(
        max_length=128, 
        verbose_name="Contraseña (Hash de seguridad)"
    )
    nombre_completo = models.CharField(
        max_length=150, 
        verbose_name="Nombre Completo"
    )
    correo = models.EmailField(
        blank=True, 
        default='', 
        verbose_name="Correo Electrónico"
    )
    rol = models.CharField(
        max_length=20, 
        choices=ROLES_USUARIO, 
        default='tecnico', 
        verbose_name="Rol en la Clínica"
    )
    telefono = models.CharField(
        max_length=25, 
        blank=True, 
        default='', 
        verbose_name="Teléfono Celular"
    )
    activo = models.BooleanField(
        default=True, 
        verbose_name="¿Cuenta Activa?"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Fecha de Registro"
    )

    class Meta:
        verbose_name = "Usuario de la Clínica"
        verbose_name_plural = "Usuarios de la Clínica"
        ordering = ['nombre_completo']

    def fijar_contrasena(self, clave_plana):
        """Encripta la contraseña con hash seguro para guardarla en la BD"""
        self.contrasena = make_password(clave_plana)

    def verificar_contrasena(self, clave_plana):
        """Valida si la contraseña ingresada coincide con la almacenada"""
        # Las contraseñas SIEMPRE se comparan contra su hash (OWASP A02 / A07): no existe comparación en texto plano
        return check_password(clave_plana, self.contrasena)

    @property
    def username(self):
        """Compatibilidad con templates"""
        return self.nombre_usuario

    def get_full_name(self):
        """Retorna el nombre completo del usuario"""
        return self.nombre_completo

    def a_diccionario(self):
        """Convierte los datos del usuario en un diccionario para la API REST JSON"""
        return {
            'id': self.id,
            'nombre_usuario': self.nombre_usuario,
            'nombre_completo': self.nombre_completo,
            'correo': self.correo,
            'rol': self.rol,
            'rol_legible': self.get_rol_display(),
            'es_admin': self.rol == 'admin',
            'es_docente': self.rol in ['docente', 'admin'],
            'es_recepcion': self.rol in ['recepcion', 'admin'],
            'es_tecnico': self.rol in ['tecnico', 'admin'],
        }

    def __str__(self):
        return f"{self.nombre_completo} ({self.nombre_usuario}) — {self.get_rol_display()}"
