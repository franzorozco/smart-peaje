"""Configuración de Django para Smart Peaje (producción en Render y desarrollo local)."""
from datetime import timedelta
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


def _split_csv(valor: str) -> list[str]:
    return [item.strip() for item in valor.split(",") if item.strip()]


DEBUG = os.environ.get("DEBUG", "False").strip().lower() in ("1", "true", "yes")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-local-insecure-key-only-for-debug"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY es obligatorio cuando DEBUG=False.")

ALLOWED_HOSTS = _split_csv(os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else ""))
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_host and render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_host)

CORS_ALLOWED_ORIGINS = _split_csv(
    os.environ.get("WEB_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else "")
)
CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "peaje",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"
_db_url = os.environ.get("DATABASE_URL", "").strip() or DEFAULT_SQLITE_URL
DATABASES = {
    "default": dj_database_url.parse(
        _db_url,
        conn_max_age=60,
    )
}

AUTH_USER_MODEL = "peaje.Usuario"

LANGUAGE_CODE = "es"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "peaje.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Smart Peaje API",
    "DESCRIPTION": "API REST para el sistema inteligente de control de peaje, tiempo real y agente consultivo.",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": None,
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Integraciones externas por variables de entorno
INFERENCE_URL = os.environ.get("INFERENCE_URL", "").strip()
INFERENCE_TOKEN = os.environ.get("INFERENCE_TOKEN", "").strip()

PUSHER_APP_ID = os.environ.get("PUSHER_APP_ID", "").strip()
PUSHER_KEY = os.environ.get("PUSHER_KEY", "").strip()
PUSHER_SECRET = os.environ.get("PUSHER_SECRET", "").strip()
PUSHER_CLUSTER = os.environ.get("PUSHER_CLUSTER", "").strip()

_raw_client_ids = _split_csv(os.environ.get("GOOGLE_CLIENT_IDS", ""))
_web_client_id = os.environ.get("GOOGLE_WEB_CLIENT_ID", "").strip()
if _web_client_id and _web_client_id not in _raw_client_ids:
    _raw_client_ids.insert(0, _web_client_id)
GOOGLE_CLIENT_IDS = _raw_client_ids

ADMIN_EMAILS = _split_csv(os.environ.get("ADMIN_EMAILS", ""))
OPERADOR_EMAILS = _split_csv(os.environ.get("OPERADOR_EMAILS", ""))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

DATA_UPLOAD_MAX_MEMORY_SIZE = 35 * 1024 * 1024
