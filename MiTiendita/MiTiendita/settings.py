"""
Django settings for MiTiendita project.
CONFIGURACIÓN CORREGIDA PARA PYTHONANYWHERE (SQLite)
"""

from pathlib import Path
import os

# 1. BASE_DIR: Carpeta principal del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: Clave secreta (en producción deberías cambiarla, pero para el proyecto sirve)
SECRET_KEY = 'django-insecure-lm$9k4_1c_qq08c4nzwuuj9&unx0^v^hprd25s(4-b+t!=b@tk'

# DEBUG activado para ver errores si salen
DEBUG = True

# Permitir que la página se vea desde cualquier lugar (incluido PythonAnywhere)
ALLOWED_HOSTS = ['*']

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

# --- CAMBIO IMPORTANTE: BASE DE DATOS SQLITE (GRATIS) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Internationalization
LANGUAGE_CODE = 'es-ni'
TIME_ZONE = 'America/Managua'
USE_I18N = True
USE_TZ = True

# --- ARCHIVOS ESTÁTICOS ---
STATIC_URL = '/static/'
# Esta carpeta es donde PythonAnywhere buscará los archivos estáticos
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
    os.path.join(BASE_DIR, "MiTiendita", "static"),
    os.path.join(BASE_DIR, "Imagenes"),
]

# --- ARCHIVOS MULTIMEDIA ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Configuración de Correo
# NOTA: Dejé tus datos, pero ten cuidado de no compartir este archivo con extraños.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'antonyjesus031@gmail.com'
EMAIL_HOST_PASSWORD = 'aiwn mdqf hadk krep'
DEFAULT_FROM_EMAIL = 'Mi Tiendita <antonyjesus031@gmail.com>'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

import os  # <--- Si 'import os' ya está arriba del todo, no lo pongas aquí.

# --- CONFIGURACIÓN DE IMÁGENES ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')