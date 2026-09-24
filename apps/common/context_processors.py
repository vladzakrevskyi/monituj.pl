from django.conf import settings

from apps.accounts.models import is_guest_account
from apps.common.analytics import gtm_id


def _received_open_count(request):
    from apps.requests.received import account_email, open_count

    user = getattr(request, "user", None)
    email = account_email(user) if user is not None else None
    # Only the panel shows it; public pages skip the query.
    if not email or not request.resolver_match or not _in_panel(request):
        return 0
    return open_count(email)


def _in_panel(request):
    return request.resolver_match.namespace in {
        "accounts",
        "clients",
        "requests",
        "notifications",
    }


def _unread_notifications(request):
    from apps.notifications.inbox import unread_count

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.resolver_match:
        return 0
    if not _in_panel(request):
        return 0
    return unread_count(user)


def site(request):
    from apps.common import cookies, seo
    from apps.common.content import SEGMENTS

    return {
        "seo": seo.for_request(request),
        "gtm_id": gtm_id(),
        "cookie_consent": cookies.consent(),
        # Legal pages must stay readable before deciding, so no cookie wall there.
        "cookie_lock": getattr(request.resolver_match, "namespace", "") != "legal",
        "footer_segments": SEGMENTS,
        "site_verification": {
            "google": settings.GOOGLE_SITE_VERIFICATION,
            "bing": settings.BING_SITE_VERIFICATION,
        },
        "received_open_count": _received_open_count(request),
        "unread_notifications": _unread_notifications(request),
        "contact_email": settings.CONTACT_EMAIL,
        "maintenance_bypass": getattr(request, "maintenance_bypass", False),
        "guest_account": is_guest_account(getattr(request, "user", None)),
    }
