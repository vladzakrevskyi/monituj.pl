from pathlib import Path

import environ

from apps.common import logging_conf

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.common",
    "apps.accounts",
    "apps.clients",
    "apps.requests",
    "apps.documents",
    "apps.reminders",
    "apps.notifications",
    "apps.audit",
    "apps.demo",
    "apps.contact",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIDMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
    # After the security headers, so the maintenance page gets them too.
    "apps.common.maintenance.MaintenanceModeMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.common.timezones.TimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.ApiExceptionMiddleware",
    "apps.common.typography.OrphansMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.demo.context_processors.demo",
                "apps.common.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

PRIVATE_STORAGE_ROOT = BASE_DIR / "storage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/logowanie/"
LOGIN_REDIRECT_URL = "/panel/"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

CONTENT_SECURITY_POLICY = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
}

PERMISSIONS_POLICY = {
    "camera": "()",
    "microphone": "()",
    "geolocation": "()",
    "payment": "()",
    "usb": "()",
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    # Every 5 minutes, so reminders leave close to their planned time.
    "send-automatic-reminders": {
        "task": "apps.reminders.tasks.send_automatic_reminders",
        "schedule": 300.0,
    },
    "anonymize-expired-documents": {
        "task": "apps.documents.tasks.anonymize_expired_documents",
        "schedule": 3600.0,
    },
    "delete-unconfirmed-requests": {
        "task": "apps.requests.tasks.delete_unconfirmed_requests",
        "schedule": 3600.0,
    },
    "delete-old-throttle-events": {
        "task": "apps.common.tasks.delete_old_throttle_events",
        "schedule": 3600.0,
    },
    "delete-expired-demo-accounts": {
        "task": "apps.demo.tasks.delete_expired_demo_accounts",
        "schedule": 3600.0,
    },
}

MAILERS = {
    "default": {
        "BACKEND": env(
            "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
        ),
        "OPTIONS": {
            "host": env("EMAIL_HOST", default=""),
            "port": env.int("EMAIL_PORT", default=587),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
        },
    },
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Monituj <no-reply@monituj.pl>")
# Contact form messages go here, and replies to any email land here unless
# a message is better answered by someone else (see EmailService).
CONTACT_EMAIL = env("CONTACT_EMAIL", default="kontakt@monituj.pl")

SITE_URL = env("SITE_URL", default="http://localhost:8000")

# Google Tag Manager container, e.g. GTM-NWZ96857. Empty = no analytics.
# See apps/common/analytics.py for where and when it loads.
GTM_ID = env("GTM_ID", default="")
# Tools loaded through GTM, keys from apps/common/cookies.py SERVICES:
# ga4, google_ads, meta_pixel, clarity, linkedin. They decide the categories in
# the cookie banner, the policies and the CSP. Ignored without GTM_ID.
TRACKING_SERVICES = env.list("TRACKING_SERVICES", default=["ga4"])

# Search Console / Bing Webmaster Tools ownership tokens (optional).
GOOGLE_SITE_VERIFICATION = env("GOOGLE_SITE_VERIFICATION", default="")
BING_SITE_VERIFICATION = env("BING_SITE_VERIFICATION", default="")

# Maintenance mode: MAINTENANCE_MODE=True shows everyone a "prace techniczne"
# page, except the addresses (or ranges like 10.0.0.0/24) listed, comma
# separated, in MAINTENANCE_ALLOWED_IPS.
MAINTENANCE_MODE = env.bool("MAINTENANCE_MODE", default=False)
MAINTENANCE_ALLOWED_IPS = env.list("MAINTENANCE_ALLOWED_IPS", default=[])

LOGGING = logging_conf.LOGGING

# Operator details shown in the Terms, Privacy policy and DPA. Anything left
# empty renders as a highlighted "[uzupelnij ...]" placeholder on those pages.
LEGAL_ENTITY = {
    "name": env("LEGAL_NAME", default=""),
    "address": env("LEGAL_ADDRESS", default=""),
    "nip": env("LEGAL_NIP", default=""),
    "regon": env("LEGAL_REGON", default=""),
    "register": env("LEGAL_REGISTER", default=""),
    "email": env("LEGAL_EMAIL", default=""),
    "privacy_email": env("LEGAL_PRIVACY_EMAIL", default=""),
    "hosting_provider": env("LEGAL_HOSTING_PROVIDER", default=""),
    "email_provider": env("LEGAL_EMAIL_PROVIDER", default=""),
    "effective_date": env("LEGAL_EFFECTIVE_DATE", default=""),
    "backup_days": env("LEGAL_BACKUP_DAYS", default=""),
    "hosting_location": env("LEGAL_HOSTING_LOCATION", default=""),
}
