from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        # The alarm (apps/common/security_watch.py).
        from django.contrib.auth import get_user_model
        from django.contrib.auth.signals import user_logged_in
        from django.db.models.signals import post_save, pre_save

        from apps.audit.models import AuditLog
        from apps.common import security_watch

        user_model = get_user_model()
        user_logged_in.connect(
            security_watch.on_login, dispatch_uid="security-staff-login"
        )
        pre_save.connect(
            security_watch.remember_rights,
            sender=user_model,
            dispatch_uid="security-rights-before",
        )
        post_save.connect(
            security_watch.rights_changed,
            sender=user_model,
            dispatch_uid="security-rights-changed",
        )
        post_save.connect(
            security_watch.on_audit, sender=AuditLog, dispatch_uid="security-audit"
        )
