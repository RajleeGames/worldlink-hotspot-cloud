import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .env import load_environment

BASE_DIR = Path(__file__).resolve().parent.parent
load_environment(BASE_DIR)

def flag(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}

DEBUG = flag('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY is required in production')
    SECRET_KEY = 'development-only-unsafe-key-change-before-hosting'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1, shows-layout-ice-reprints.trycloudflare.com',).split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [h.strip() for h in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if h.strip()]
ALLOW_PUBLIC_SIGNUP = flag('ALLOW_PUBLIC_SIGNUP', DEBUG)

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'cloud', 'tenants', 'networks', 'vouchers', 'hotspots', 'controlcenter', 'portal', 'payments',
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
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug', 'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
        'cloud.context_processors.shell_context',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

if os.environ.get('DB_ENGINE', '').lower() == 'postgresql':
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'worldlink_hotspot'),
        'USER': os.environ.get('DB_USER', 'worldlink'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'en'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'cloud:dashboard'
LOGOUT_REDIRECT_URL = 'login'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = flag('SECURE_SSL_REDIRECT', False) if not DEBUG else False
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if flag('TRUST_PROXY_SSL_HEADER', False) else None
X_FRAME_OPTIONS = 'DENY'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'

# EvPay pilot (default: OFF). Use one approved merchant for ONE pilot company only.
# Do not enable live collections until you have verified sandbox callbacks.
EVPAY_ENABLED = flag('EVPAY_ENABLED', False)
EVPAY_ENVIRONMENT = os.environ.get('EVPAY_ENVIRONMENT', 'sandbox').strip().lower()
EVPAY_PRODUCTION_CHARGES_ENABLED = flag('EVPAY_PRODUCTION_CHARGES_ENABLED', False)
EVPAY_COMPANY_ID = int(os.environ.get('EVPAY_COMPANY_ID') or '0')
EVPAY_BASE_URL = os.environ.get('EVPAY_BASE_URL', '').rstrip('/')
EVPAY_PUBLIC_BASE_URL = os.environ.get('EVPAY_PUBLIC_BASE_URL', '').rstrip('/')
EVPAY_CLIENT_ID = os.environ.get('EVPAY_CLIENT_ID', '')
EVPAY_CLIENT_SECRET = os.environ.get('EVPAY_CLIENT_SECRET', '')
EVPAY_SIG_KEY = os.environ.get('EVPAY_SIG_KEY', '')
EVPAY_WEBHOOK_SECRET = os.environ.get('EVPAY_WEBHOOK_SECRET', '')
EVPAY_WEBHOOK_TOKEN = os.environ.get('EVPAY_WEBHOOK_TOKEN', '')
