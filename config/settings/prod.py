from django.core.exceptions import ImproperlyConfigured

from .base import *

# Documents are never stored unencrypted in production.
if not DOCUMENTS_ENCRYPTION_KEY:  # noqa: F405
    raise ImproperlyConfigured(
        "Set DOCUMENTS_ENCRYPTION_KEY - generate one with: python3 -c \"import "
        "os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\" "
        "(README: 'Szyfrowanie dokumentów')."
    )

DEBUG = False

# nginx terminates HTTPS and passes the original scheme in this header;
# without it every request looks like plain HTTP and SECURE_SSL_REDIRECT
# would redirect forever.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files are served by WhiteNoise from the web container, compressed
# and with hashed names so browsers can cache them forever.
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
