"""
Configuración principal de Django para el proyecto Clínica del PC INACAP.
Desarrollado como prototipo funcional para la asignatura de Ingeniería de Software.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# CONFIGURACIÓN SEGURA POR VARIABLES DE ENTORNO (OWASP A02 / A05)
# Los secretos y los modos de ejecución ya no están escritos en el código.
#   CLINICA_DEBUG=0          -> modo producción (por defecto es 1 = desarrollo local)
#   CLINICA_SECRET_KEY=...   -> obligatoria cuando CLINICA_DEBUG=0
#   CLINICA_ALLOWED_HOSTS=a,b -> hosts permitidos (por defecto solo localhost)
# ==============================================================================
DEBUG = os.environ.get('CLINICA_DEBUG', '1') == '1'

SECRET_KEY = os.environ.get('CLINICA_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Falta la variable de entorno CLINICA_SECRET_KEY en modo producción.')
    # Clave solo para desarrollo local: nunca se usa si DEBUG está apagado
    SECRET_KEY = 'django-insecure-solo-desarrollo-local-clinica-pc'

# Solo se aceptan peticiones dirigidas a estos hosts (evita Host Header Injection)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('CLINICA_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',') if h.strip()]

# ==============================================================================
# APLICACIONES INSTALADAS (Módulos de nuestra aplicación)
# ==============================================================================
INSTALLED_APPS = [
    # Módulos predeterminados de Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Módulos personalizados que creamos para la Clínica del PC:
    'autenticacion',  # Módulo para control de usuarios, login y roles
    'gestion',        # Módulo de base de datos (Propietarios, Equipos, Órdenes)
    'api',            # Módulo de la API REST para enviar y recibir datos en JSON
    'portal',         # Módulo que muestra las páginas HTML al usuario
]

# Middlewares para seguridad, sesiones y autenticación
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# Configuración de plantillas HTML
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Indicamos a Django dónde buscar los archivos HTML (carpeta templates)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'portal.contexto.token_csrf',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ==============================================================================
# BASE DE DATOS LOCAL (SQLite)
# ==============================================================================
# Usamos SQLite porque es local, ligera y no requiere instalar servicios externos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Validaciones de contraseñas
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
]

# ==============================================================================
# SEGURIDAD DE SESIONES, COOKIES Y CABECERAS (OWASP A05 / A07)
# ==============================================================================
SESSION_COOKIE_HTTPONLY = True        # el JavaScript de la página no puede leer la cookie de sesión
SESSION_COOKIE_SAMESITE = 'Lax'       # la cookie no viaja en peticiones originadas desde otros sitios
SESSION_COOKIE_AGE = 8 * 60 * 60      # la sesión expira a las 8 horas (una jornada)
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'              # la aplicación no puede incrustarse en otros sitios (clickjacking)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

if not DEBUG:
    # En producción (HTTPS) las cookies solo viajan cifradas
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get('CLINICA_SSL_REDIRECT', '1') == '1'
    SECURE_HSTS_SECONDS = 31536000

# ==============================================================================
# BITÁCORA DE SEGURIDAD (OWASP A09): logins fallidos, bloqueos y acciones sensibles
# ==============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'seguridad': {'format': '{asctime} [{levelname}] {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'consola': {'class': 'logging.StreamHandler', 'formatter': 'seguridad'},
    },
    'loggers': {
        'clinica': {'handlers': ['consola'], 'level': 'INFO', 'propagate': False},
    },
}

# Configuración regional de idioma y zona horaria (Chile)
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# ==============================================================================
# ARCHIVOS ESTÁTICOS (CSS, JS, Imágenes)
# ==============================================================================
# URL para acceder a los archivos estáticos en el navegador
STATIC_URL = '/static/'

# Carpeta física donde guardamos nuestros archivos CSS y JavaScript
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# URL a la que se redirige si un usuario no está logueado
LOGIN_URL = '/login/'

# Clave primaria por defecto para los modelos
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
