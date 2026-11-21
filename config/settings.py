import os
import ipaddress
import hashlib
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
    'cloud', 'tenants', 'networks', 'vouchers', 'hotspots', 'controlcenter', 'portal', 'payments', 'wallets',
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
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': Path(os.environ.get('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3'))), 'OPTIONS': {'timeout': 20}}}

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
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT_PATH', str(BASE_DIR / 'media')))
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Content fingerprints make the browser fetch new CSS/JS after every deployment,
# even when Nginx or Cloudflare caches /static/ with a long lifetime.
APP_CSS_VERSION = hashlib.sha256((BASE_DIR / 'static/css/app.css').read_bytes()).hexdigest()[:12]
APP_JS_VERSION = hashlib.sha256((BASE_DIR / 'static/js/app.js').read_bytes()).hexdigest()[:12]
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
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0')) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if flag('TRUST_PROXY_SSL_HEADER', False) else None
X_FRAME_OPTIONS = 'DENY'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'

# Opt-in router management only across explicitly authorized private LAN/VPN ranges.
# Example: MIKROTIK_ALLOWED_CIDRS=192.168.88.1/32,10.8.0.0/24
MIKROTIK_ALLOWED_CIDRS = tuple(
    ipaddress.ip_network(item.strip(), strict=False)
    for item in os.environ.get('MIKROTIK_ALLOWED_CIDRS', '').split(',') if item.strip()
)
MIKROTIK_CA_FILE = os.environ.get('MIKROTIK_CA_FILE', '').strip()

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

# Separate, explicitly approved multi-business collection pilot. WorldLink is
# the sole EvPay merchant; the business IDs are accounting attribution only.
# Disable by default, especially until the merchant agreement permits this.
EVPAY_PUBLIC_CHECKOUT_ENABLED = flag('EVPAY_PUBLIC_CHECKOUT_ENABLED', False)
EVPAY_COLLECTION_COMPANY_IDS = {
    int(item) for item in os.environ.get('EVPAY_COLLECTION_COMPANY_IDS', '').split(',')
    if item.strip().isdigit() and int(item) > 0
}
EVPAY_COLLECTION_WEBHOOK_TOKEN = os.environ.get('EVPAY_COLLECTION_WEBHOOK_TOKEN', '')
EVPAY_PUBLIC_MAX_AMOUNT_TZS = int(os.environ.get('EVPAY_PUBLIC_MAX_AMOUNT_TZS') or '1000')

# Real-money public USSD throttling must work across every gunicorn worker.
# Never rely on Django's default per-process LocMemCache for live payments.
WHC_REDIS_URL = os.environ.get('WHC_REDIS_URL', '').strip()
if WHC_REDIS_URL:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                           'LOCATION': WHC_REDIS_URL,
                           'KEY_PREFIX': 'worldlink-hotspot'}}

# One EAP/one company pilot. Additional independent businesses require an
# explicitly configured controller and verified merchant/submerchant agreement.
OMADA_LIVE_ENABLED = flag('OMADA_LIVE_ENABLED', False)
EVPAY_MULTITENANT_ENABLED = flag('EVPAY_MULTITENANT_ENABLED', False)
OMADA_PILOT_COMPANY_ID = int(os.environ.get('OMADA_PILOT_COMPANY_ID') or '0')
OMADA_CONTROLLER_URL = os.environ.get('OMADA_CONTROLLER_URL', '').rstrip('/')
OMADA_CONTROLLER_ID = os.environ.get('OMADA_CONTROLLER_ID', '')
OMADA_OPERATOR_NAME = os.environ.get('OMADA_OPERATOR_NAME', '')
OMADA_OPERATOR_PASSWORD = os.environ.get('OMADA_OPERATOR_PASSWORD', '')
OMADA_CA_FILE = os.environ.get('OMADA_CA_FILE', '')
OMADA_AP_MAC = os.environ.get('OMADA_AP_MAC', '').upper()
OMADA_SSID = os.environ.get('OMADA_SSID', '')

# Public *device inform* hostname on the central controller, not a login URL.
# Assigned to customers only after WorldLink reviews their Omada request.
OMADA_CENTRAL_INFORM_HOST = os.environ.get('OMADA_CENTRAL_INFORM_HOST', '').strip()

# Optional, read-only Open API monitoring (pilot and approved central sites).
# Keep credentials on the VPS, never in tenant forms or version control.
OMADA_OPENAPI_CLIENT_ID = os.environ.get('OMADA_OPENAPI_CLIENT_ID', '').strip()
OMADA_OPENAPI_CLIENT_SECRET = os.environ.get('OMADA_OPENAPI_CLIENT_SECRET', '').strip()
OMADA_OPENAPI_API_KEY = os.environ.get('OMADA_OPENAPI_API_KEY', '').strip()
OMADA_OPENAPI_SITE_ID = os.environ.get('OMADA_OPENAPI_SITE_ID', '').strip()


# WorldLink platform subscription billing; disabled until live test and launch approval.
WORLDLINK_SUBSCRIPTIONS_ENABLED = flag('WORLDLINK_SUBSCRIPTIONS_ENABLED', False)
WORLDLINK_SUBSCRIPTIONS_ENFORCED = flag('WORLDLINK_SUBSCRIPTIONS_ENFORCED', False)
EVPAY_SUBSCRIPTION_WEBHOOK_TOKEN = os.environ.get('EVPAY_SUBSCRIPTION_WEBHOOK_TOKEN', '')
