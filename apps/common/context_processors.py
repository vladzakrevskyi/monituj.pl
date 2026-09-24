from django.conf import settings

from apps.accounts.models import is_guest_account


def site(request):
    return {
        "contact_email": settings.CONTACT_EMAIL,
        "maintenance_bypass": getattr(request, "maintenance_bypass", False),
        "guest_account": is_guest_account(getattr(request, "user", None)),
    }
