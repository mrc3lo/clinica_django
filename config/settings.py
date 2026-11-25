"""
Configuración principal de Django para el proyecto Clínica del PC INACAP.
Desarrollado como prototipo funcional para la asignatura de Ingeniería de Software.
"""

from pathlib import Path

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Clave secreta para desarrollo local
SECRET_KEY = 'django-insecure-clinica-pc-inacap-clave-secreta-estudiante-2026'

# Modo depuración activo para ver errores claramente durante el desarrollo
DEBUG = True

# Permitimos conexiones locales
ALLOWED_HOSTS = ['*']

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
        'OPTIONS': {'min_length': 4},  # Mínimo 4 caracteres para pruebas fáciles
    },
]

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
