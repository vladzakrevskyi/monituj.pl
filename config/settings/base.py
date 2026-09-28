from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

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
    "apps.consents",
    "apps.audit",
    "apps.demo",
    "apps.contact",
    "apps.billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIDMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
    # After the security headers, so the maintenance page gets them too.
    "apps.common.maintenance.MaintenanceModeMiddleware",
    "apps.common.admin_security.AdminAccessMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.common.timezones.TimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.ApiExceptionMiddleware",
    # Keeps the panel closed until changed Terms are accepted.
    "apps.consents.middleware.LegalAcceptanceMiddleware",
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

# Address of the Django admin. Moving it off the obvious /admin/ keeps bots
# from even finding the login; nginx should allow it only from your IP.
ADMIN_URL = env("ADMIN_URL", default="admin/").strip("/") + "/"
# Addresses (or ranges like 10.0.0.0/24) allowed to open the admin, comma
# separated. Empty = no limit (fine locally; set it on the server).
ADMIN_ALLOWED_IPS = env.list("ADMIN_ALLOWED_IPS", default=[])
# Master key for encrypting uploaded documents at rest (AES-256-GCM, see
# apps/documents/encryption.py). Generate: README 'Szyfrowanie dokumentów'.
# Required in production. Keep a copy outside the
# server: without it the stored documents can't be read.
DOCUMENTS_ENCRYPTION_KEY = env("DOCUMENTS_ENCRYPTION_KEY", default="")
# Previous master keys while rotating (comma separated) - decrypt only.
DOCUMENTS_ENCRYPTION_OLD_KEYS = env.list("DOCUMENTS_ENCRYPTION_OLD_KEYS", default=[])

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
    # Plan purchase forms redirect to Stripe's Checkout and customer portal.
    "form-action": "'self' https://checkout.stripe.com https://billing.stripe.com",
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
    # "Nowy dokument" emails to senders, once the recipient stops uploading.
    "send-upload-emails": {
        "task": "apps.notifications.tasks.send_upload_emails",
        "schedule": 60.0,
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
    "delete-old-cookie-consents": {
        "task": "apps.consents.tasks.delete_old_cookie_consents",
        "schedule": 86400.0,
    },
    # VAT invoices for paid Stripe invoices: create in inFakt, then email.
    "issue-vat-invoices": {
        "task": "apps.billing.tasks.issue_invoices",
        "schedule": 60.0,
    },
    # Emails about plan changes, queued by Stripe syncs.
    "send-billing-notices": {
        "task": "apps.billing.tasks.send_notices",
        "schedule": 60.0,
    },
    # Trial reminders and cleanup of handled Stripe webhook events.
    "billing-daily": {
        "task": "apps.billing.tasks.daily",
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

# Sign in with Google (OAuth client of type "Web application" in Google
# Cloud Console). Both empty = the Google buttons are not shown at all.
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")

# Payments (Stripe). STRIPE_MODE picks the keys in use: "sandbox" (test
# cards, no real money) or "live". Each mode has its own secret key and
# webhook signing secret; empty secret key = the plan can't be bought.
# Products and prices are created by `manage.py stripe_setup` (README).
STRIPE_MODE = env("STRIPE_MODE", default="sandbox").strip().lower()
if STRIPE_MODE not in ("sandbox", "live"):
    raise ImproperlyConfigured("STRIPE_MODE must be 'sandbox' or 'live'.")
STRIPE_KEYS = {
    mode: {
        "secret_key": env(f"STRIPE_{mode.upper()}_SECRET_KEY", default=""),
        "webhook_secret": env(f"STRIPE_{mode.upper()}_WEBHOOK_SECRET", default=""),
    }
    for mode in ("sandbox", "live")
}
# A live key in the sandbox slot (or the other way round) would charge real
# cards while testing - refuse to start instead.
for _mode, _prefix in (("sandbox", "_test_"), ("live", "_live_")):
    _key = STRIPE_KEYS[_mode]["secret_key"]
    if _key and _key[2:8] != _prefix:
        raise ImproperlyConfigured(
            f"STRIPE_{_mode.upper()}_SECRET_KEY must be an sk{_prefix}... "
            f"or rk{_prefix}... key."
        )
# VAT invoices (inFakt). INFAKT_MODE picks the account: "sandbox"
# (api.sandbox-infakt.pl, test invoices) or "live" (api.infakt.pl). Each mode
# has its own API key (scopes api:invoices:read + api:invoices:write) and
# webhook secret (from the webhook's details in inFakt). Empty key = no
# invoices are issued. INFAKT_SEND_TO_KSEF: send each invoice to KSeF
# (needs the KSeF integration switched on in inFakt).
INFAKT_MODE = env("INFAKT_MODE", default="sandbox").strip().lower()
if INFAKT_MODE not in ("sandbox", "live"):
    raise ImproperlyConfigured("INFAKT_MODE must be 'sandbox' or 'live'.")
INFAKT_KEYS = {
    mode: {
        "api_key": env(f"INFAKT_{mode.upper()}_API_KEY", default=""),
        "webhook_secret": env(f"INFAKT_{mode.upper()}_WEBHOOK_SECRET", default=""),
    }
    for mode in ("sandbox", "live")
}
INFAKT_API_URLS = {
    "sandbox": "https://api.sandbox-infakt.pl/api/v3",
    "live": "https://api.infakt.pl/api/v3",
}
INFAKT_SEND_TO_KSEF = env.bool("INFAKT_SEND_TO_KSEF", default=False)

# Firm details by NIP from the GUS REGON database (BIR 1.1) - every firm,
# VAT payer or not. GUS_MODE=test uses GUS's public test key and its
# anonymised test data (fine locally); production needs a free key from
# GUS (https://api.stat.gov.pl/Home/RegonApi). Without it only the Ministry
# of Finance VAT register is asked.
GUS_MODE = env("GUS_MODE", default="test").strip().lower()
if GUS_MODE not in ("test", "production"):
    raise ImproperlyConfigured("GUS_MODE must be 'test' or 'production'.")
GUS_API_KEY = env("GUS_API_KEY", default="")

# VAT added to plan prices (net) in percent; 0 when the seller is VAT-exempt.
BILLING_VAT_RATE = env.int("BILLING_VAT_RATE", default=23)

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
    # Optional: a CDN / proxy all traffic passes through (e.g. Cloudflare).
    "cdn_provider": env("LEGAL_CDN_PROVIDER", default=""),
    "effective_date": env("LEGAL_EFFECTIVE_DATE", default=""),
    "backup_days": env("LEGAL_BACKUP_DAYS", default=""),
    "hosting_location": env("LEGAL_HOSTING_LOCATION", default=""),
}
