"""
Django settings for MiTiendita project.
CONFIGURACIÓN PORTÁTIL (Funciona en cualquier PC)
"""

from pathlib import Path
from decouple import config
import os

# 1. BASE_DIR: Es la carpeta principal de tu proyecto.
# Django la detecta automáticamente donde sea que esté guardado el proyecto.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-lm$9k4_1c_qq08c4nzwuuj9&unx0^v^hprd25s(4-b+t!=b@tk'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'tienda',   # Tu app principal
    'usuarios', # Tu app de usuarios
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'MiTiendita.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            # --- CORRECCIÓN CLAVE ---
            # En lugar de "C:\Users\...", usamos BASE_DIR.
            # Esto le dice a Django: "Busca la carpeta templates DENTRO de la carpeta tienda".
            os.path.join(BASE_DIR, 'tienda', 'templates'),
        ],
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

WSGI_APPLICATION = 'MiTiendita.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': config('DB_NAME', default='django_sqlserver'),
        'USER': config('DB_USER', default='django_user'),
        'PASSWORD': config('DB_PASSWORD', default='dj@ng0'),
        'HOST': config('DB_HOST', default='DESKTOP-CEIJPA0'),
        'PORT': config('DB_PORT', default='1433'),
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'encrypt': 'no',
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-ni' 
TIME_ZONE = 'America/Managua'
USE_I18N = True
USE_TZ = True

# --- ARCHIVOS ESTÁTICOS (CSS, JS, IMÁGENES FIJAS) ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
    os.path.join(BASE_DIR, "MiTiendita", "static"),
    os.path.join(BASE_DIR, "Imagenes"),
]

# --- ARCHIVOS MULTIMEDIA (FOTOS QUE SUBE LA DUEÑA) ---
# 1. URL pública para ver la foto en el navegador
MEDIA_URL = '/media/'

# 2. RUTA FÍSICA donde se guardan las fotos en el disco duro.
# Usando os.path.join(BASE_DIR, 'media'), Django creará la carpeta "media"
# automáticamente dentro de tu proyecto, en cualquier computadora.
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# Configuración de Correo
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'antonychavarria2006@gmail.com'
EMAIL_HOST_PASSWORD = 'bnff jesz qwrv delq'
DEFAULT_FROM_EMAIL = 'Mi Tiendita <antonychavarria2006@gmail.com>'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
