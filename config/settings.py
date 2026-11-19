"""
Configuración del sistema de protocolos de investigación (Centro de Ojos Loria).

Los secretos se leen de variables de entorno; en desarrollo hay valores
por defecto que NUNCA deben usarse en producción.
"""
import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
EN_PRUEBAS = "test" in sys.argv

_CLAVE_DESARROLLO = "solo-desarrollo-cambiar-en-produccion"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _CLAVE_DESARROLLO)

# Seguro por defecto: DEBUG solo si se pide explícitamente (DJANGO_DEBUG=1).
# Antes el valor por defecto era "1": si en producción faltaba la variable,
# la app arrancaba mostrando trazas con datos internos.
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

if not DEBUG and not EN_PRUEBAS and SECRET_KEY == _CLAVE_DESARROLLO:
    raise RuntimeError(
        "DJANGO_SECRET_KEY no está definida: la app no arranca en producción con la clave de desarrollo."
    )

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes",
    "cuentas",
    "estudios",
    "finanzas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "cuentas.middleware.ObligarCambioClaveMiddleware",
]

# Bloqueo de intentos de acceso fallidos (django-axes).
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_ENABLED = not EN_PRUEBAS
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # horas: 15 minutos bloqueado
AXES_RESET_ON_SUCCESS = True
# Bloqueo por usuario: frena la fuerza bruta contra una cuenta. Contracara:
# cualquiera que conozca un nombre de usuario puede dejarlo bloqueado 15 min
# (ver auditoría de seguridad, hallazgo sobre lockout). Detrás del proxy de
# Render la IP real llega en X-Forwarded-For (un solo salto).
AXES_LOCKOUT_PARAMETERS = ["username"]
AXES_IPWARE_PROXY_COUNT = 1
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "estudios.contexto.protocolos",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("DATABASE_URL"):
    # Producción: la URL completa la da Render.
    DATABASES = {"default": dj_database_url.config(conn_max_age=600, ssl_require=True)}
else:
    # Desarrollo y pruebas: un archivo local, sin instalar nada.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "desarrollo.sqlite3"}}

AUTH_USER_MODEL = "cuentas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True  # $ 2.500.000,00

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # En desarrollo y en las pruebas no hace falta correr collectstatic.
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if (DEBUG or EN_PRUEBAS)
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sesiones: expiran a las 12 horas; la cookie no es accesible desde JS.
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Registro de errores a la salida estándar (Render los guarda). Los datos
# personales no viajan en las URLs (solo IDs), salvo el parámetro de búsqueda.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": "WARNING"},
    "loggers": {
        "django.security": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
    },
}

if not DEBUG and not EN_PRUEBAS:
    # Endurecimiento para producción (detrás de HTTPS). En las pruebas no se
    # fuerza HTTPS: así la suite pasa sin tener que poner DJANGO_DEBUG=1 a mano
    # (antes fallaban 312 pruebas por la redirección). Producción no cambia.
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# El bloqueo por usuario es deliberado (igual que en la app de presupuestos).
SILENCED_SYSTEM_CHECKS = ["axes.W006"]

# La cotización del Banco Nación se consulta en línea (no durante las pruebas).
COTIZACION_EN_LINEA = not EN_PRUEBAS
