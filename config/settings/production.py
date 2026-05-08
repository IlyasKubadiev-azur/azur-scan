"""Production settings overrides. Apply behind a TLS-terminating reverse proxy."""
from .base import *  # noqa: F401, F403

DEBUG = False

# Trust X-Forwarded-* from the reverse proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"

# HSTS — enable after confirming HTTPS works end-to-end
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
