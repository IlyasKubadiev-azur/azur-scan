"""Local development settings."""
from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

INTERNAL_IPS = ["127.0.0.1"]

# Slacker password validators in dev so superuser creation isn't painful
AUTH_PASSWORD_VALIDATORS = []  # noqa: F811

# Optional: print emails to console in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
