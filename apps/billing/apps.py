from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    verbose_name = "Płatności"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.accounts.models import User
        from apps.billing.services import start_trial

        post_save.connect(start_trial, sender=User, dispatch_uid="billing-trial")
