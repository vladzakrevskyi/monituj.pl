from django.db import models

from apps.accounts.models import User

DEMO_EMAIL_DOMAIN = "demo.invalid"


class DemoAccount(models.Model):
    """Marks a throwaway account created by "Wypróbuj demo". The user and
    everything it owns are deleted once expires_at passes."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="demo_account"
    )
    ip_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self):
        return f"Demo {self.user_id} (do {self.expires_at:%Y-%m-%d %H:%M})"


def is_demo_user(user) -> bool:
    return bool(user and user.is_authenticated and hasattr(user, "demo_account"))
