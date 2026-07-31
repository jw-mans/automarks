import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")




DEBUG = os.getenv("DEBUG", "1") == "1"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")






INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "marks",
    "widget_tweaks",
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'config.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'config.wsgi.application'








DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "postgres"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}


# Global warehouse (remote Postgres, schema `activation_data`) — same target as
# scripts/sync_to_global.sh. Used only for direct writes to the TikTok funnels
# reference table via connections["global"]; Django never migrates or routes ORM
# models here (see marks.db_routers.GlobalWarehouseRouter).
GLOBAL_DB_SCHEMA = os.getenv("GLOBAL_PGSCHEMA", "activation_data")
GLOBAL_DB_HOST = os.getenv("GLOBAL_PGHOST", "")
if GLOBAL_DB_HOST:
    DATABASES["global"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("GLOBAL_PGDB", ""),
        "USER": os.getenv("GLOBAL_PGUSER", ""),
        "PASSWORD": os.getenv("GLOBAL_PGPASSWORD", ""),
        "HOST": GLOBAL_DB_HOST,
        "PORT": os.getenv("GLOBAL_PGPORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("GLOBAL_PGSSLMODE", "require")},
        # Never run automarks' schema migrations against the shared warehouse.
        "TEST": {"MIRROR": "default"},
    }

DATABASE_ROUTERS = ["marks.db_routers.GlobalWarehouseRouter"]








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








LANGUAGE_CODE = 'ru-ru'


TIME_ZONE = 'UTC'


USE_I18N = True


USE_TZ = True








STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'






DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'


CSRF_TRUSTED_ORIGINS = [
    "https://automarks.tw1.ru",
    "https://www.automarks.tw1.ru"
]


TELEGRAM_NOTIFY_BOT_TOKEN = os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "")
TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID = os.getenv("TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID", "")
TELEGRAM_NOTIFY_STATUS_CHAT_ID = os.getenv("TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
# Chat for "new TikTok funnel request" notifications to developers.
# Falls back to the new-tasks chat when unset.
TELEGRAM_NOTIFY_TIKTOK_CHAT_ID = os.getenv(
    "TELEGRAM_NOTIFY_TIKTOK_CHAT_ID", TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID
)
TASKS_PLATFORM_NAME = os.getenv("TASKS_PLATFORM_NAME", "")
WEEKLY_TASKS_REPORT_CHAT_ID = os.getenv("WEEKLY_TASKS_REPORT_CHAT_ID", "")
WEEKLY_TASKS_REPORT_TZ = os.getenv("WEEKLY_TASKS_REPORT_TZ", "Europe/Moscow")
TASKS_TIME_ZONE = os.getenv("TASKS_TIME_ZONE", TIME_ZONE or "UTC")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
