"""Base settings — shared across all environments.

Environment-specific overrides live in local.py / production.py / test.py.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-CHANGE-ME")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    # django-unfold (must come before django.contrib.admin)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.assets",
    "apps.agents",
    "apps.scanning",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise must come right after SecurityMiddleware. Serves /static/
    # via WSGI so we don't need nginx in front of gunicorn.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware activates the language from session/cookie/Accept-Language.
    # Must come after SessionMiddleware and before CommonMiddleware.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://azurscan:azurscan@localhost:5432/azurscan",
    ),
}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]


# ---------------------------------------------------------------------------
# I18N / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en"
# Storage layer keeps all timestamps in UTC (USE_TZ=True). TIME_ZONE only
# affects what humans see in the admin UI and what naive datetime literals
# in code interpret as. Moscow time = UTC+3 with no DST since 2014.
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("ru", "Русский"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise: compress + cache static files. No manifest in dev to avoid
# requiring collectstatic on every change.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
WHITENOISE_USE_FINDERS = True  # serve files from app static dirs in dev
WHITENOISE_AUTOREFRESH = True  # rescan static files on each request in dev


# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.agents.auth.AgentJWTAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.api.throttles.BurstAnonThrottle",
        "apps.api.throttles.UserScopedThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "600/min",
        "agent": "120/min",
        "enroll": "5/min",
        "login": "10/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("USER_JWT_SECRET", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ---------------------------------------------------------------------------
# Agent JWT (separate signing secret from user JWT)
# ---------------------------------------------------------------------------
AGENT_JWT_SECRET = env("AGENT_JWT_SECRET", default="dev-agent-secret-CHANGE-ME")
AGENT_ACCESS_TOKEN_TTL = timedelta(hours=24)
AGENT_REFRESH_TOKEN_TTL = timedelta(days=90)
AGENT_OFFLINE_AFTER = timedelta(minutes=5)
# 15s heartbeat gives near-instant reaction to "Run scan now" without
# producing meaningful network/CPU pressure. The interval is pushed to the
# agent in the enroll response; old agents that cached 90s will refresh on
# their next enroll/re-enroll.
AGENT_HEARTBEAT_INTERVAL_S = env.int("AGENT_HEARTBEAT_INTERVAL_S", default=15)
AGENT_FULL_SCAN_INTERVAL_H = env.int("AGENT_FULL_SCAN_INTERVAL_H", default=6)


# ---------------------------------------------------------------------------
# Spectacular (OpenAPI)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Azur-Scan API",
    "DESCRIPTION": "IT asset inventory backend.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE = "Europe/Moscow"  # beat schedules read in MSK
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://localhost:6379/2"),
    },
}


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "azurscan": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}


# ---------------------------------------------------------------------------
# LDAP (opt-in via env)
# ---------------------------------------------------------------------------
LDAP_ENABLED = env.bool("LDAP_ENABLED", default=False)
if LDAP_ENABLED:
    import ldap
    from django_auth_ldap.config import ActiveDirectoryGroupType, LDAPSearch

    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]
    AUTH_LDAP_SERVER_URI = env("AUTH_LDAP_SERVER_URI")
    AUTH_LDAP_BIND_DN = env("AUTH_LDAP_BIND_DN")
    AUTH_LDAP_BIND_PASSWORD = env("AUTH_LDAP_BIND_PASSWORD")
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        env("AUTH_LDAP_USER_SEARCH_BASE"),
        ldap.SCOPE_SUBTREE,
        "(sAMAccountName=%(user)s)",
    )
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
        env("AUTH_LDAP_GROUP_SEARCH_BASE"),
        ldap.SCOPE_SUBTREE,
        "(objectClass=group)",
    )
    AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }
    AUTH_LDAP_USER_FLAGS_BY_GROUP = {
        "is_staff": env("AUTH_LDAP_OPERATORS_GROUP_DN", default=""),
        "is_superuser": env("AUTH_LDAP_ADMINS_GROUP_DN", default=""),
    }
    AUTH_LDAP_CACHE_TIMEOUT = 300


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# ---------------------------------------------------------------------------
# django-unfold (admin theme)
# ---------------------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": "Azur-Scan",
    "SITE_HEADER": "Azur-Scan",
    "SITE_SUBHEADER": "IT Asset Inventory",
    "SITE_URL": "/",
    "SITE_SYMBOL": "monitor_heart",  # Material Symbols icon
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_LANGUAGES": True,  # language dropdown in admin header
    "ENVIRONMENT": "apps.core.unfold.environment_callback",
    "DASHBOARD_CALLBACK": "apps.core.unfold.dashboard_callback",
    "COLORS": {
        "primary": {
            "50":  "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
            "950": "23 37 84",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Inventory",
                "separator": True,
                "items": [
                    {
                        "title": "Assets",
                        "icon": "devices",
                        "link": "/admin/assets/asset/",
                    },
                    {
                        "title": "Asset types",
                        "icon": "category",
                        "link": "/admin/assets/assettype/",
                    },
                    {
                        "title": "Owner history",
                        "icon": "history",
                        "link": "/admin/assets/assetownerhistory/",
                    },
                ],
            },
            {
                "title": "Scanning",
                "separator": True,
                "items": [
                    {
                        "title": "Scan sessions",
                        "icon": "radar",
                        "link": "/admin/scanning/scansession/",
                    },
                ],
            },
            {
                "title": "Access",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/accounts/user/",
                    },
                    {
                        "title": "Roles",
                        "icon": "badge",
                        "link": "/admin/accounts/role/",
                    },
                    {
                        "title": "Audit log",
                        "icon": "fact_check",
                        "link": "/admin/core/auditlog/",
                    },
                ],
            },
            {
                "title": "Tools",
                "separator": True,
                "items": [
                    {
                        "title": "API docs (Swagger)",
                        "icon": "api",
                        "link": "/api/docs/",
                    },
                    {
                        "title": "Health",
                        "icon": "favorite",
                        "link": "/healthz",
                    },
                ],
            },
        ],
    },
}
