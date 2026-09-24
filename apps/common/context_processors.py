from django.conf import settings

from apps.accounts.models import is_guest_account


def _received_open_count(request):
    from apps.requests.received import account_email, open_count

    user = getattr(request, "user", None)
    email = account_email(user) if user is not None else None
    # Only the panel shows it; public pages skip the query.
    if not email or not request.resolver_match or not _in_panel(request):
        return 0
    return open_count(email)


def _in_panel(request):
    return request.resolver_match.namespace in {"accounts", "clients", "requests"}


def site(request):
    return {
        "received_open_count": _received_open_count(request),
        "contact_email": settings.CONTACT_EMAIL,
        "maintenance_bypass": getattr(request, "maintenance_bypass", False),
        "guest_account": is_guest_account(getattr(request, "user", None)),
    }
