from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from apps.accounts import team

        user_logged_in.connect(
            team.join_after_login, dispatch_uid="team-join-after-login"
        )
