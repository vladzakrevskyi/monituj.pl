LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging_filters.RequestIDLogFilter"},
        "redact_sensitive": {"()": "apps.common.logging_filters.RedactionFilter"},
    },
    "formatters": {
        "structured": {
            "format": (
                "%(asctime)s level=%(levelname)s logger=%(name)s "
                "request_id=%(request_id)s message=%(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["request_id", "redact_sensitive"],
        },
        # Errors to ADMINS by email - without request data (error_mail.py).
        "error_mail": {
            "()": "apps.common.error_mail.ErrorEmailHandler",
            "filters": ["request_id", "redact_sensitive"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # A page that crashed (500).
        "django.request": {
            "handlers": ["console", "error_mail"],
            "level": "INFO",
            "propagate": False,
        },
        "monituj": {
            "handlers": ["console", "error_mail"],
            "level": "INFO",
            "propagate": False,
        },
        # A background task that failed (emails, reminders, invoices).
        "celery.app.trace": {
            "handlers": ["console", "error_mail"],
            "level": "INFO",
            "propagate": False,
        },
        # The Stripe library logs every API call at INFO; only problems matter.
        "stripe": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
