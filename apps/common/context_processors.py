from django.conf import settings

from apps.accounts.google import enabled as google_login_enabled
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
        "billing",
    }


def _unread_notifications(request):
    from apps.notifications.inbox import unread_count

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.resolver_match:
        return 0
    if not _in_panel(request):
        return 0
    # A team whose access waits shows nothing of its own.
    if request.membership is not None:
        from apps.accounts import team

        if not team.has_access(request.membership):
            return 0
    return unread_count(request.account)


def _plan_state(request):
    from apps.billing.services import state_for
    from apps.demo.models import is_demo_user

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.resolver_match:
        return None
    # In a team's workspace the plan is the owner's - no banners there.
    if not _in_panel(request) or is_demo_user(user) or request.membership:
        return None
    return state_for(user)


def _workspaces(request):
    """The switcher in the panel - only for people in some team."""
    from apps.accounts import team

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not request.resolver_match:
        return []
    if not _in_panel(request) or not user.memberships.exists():
        return []
    current = request.account.pk
    return [dict(w, current=w["owner"].pk == current) for w in team.workspaces(user)]


def site(request):
    from apps.common import cookies, seo
    from apps.common.content import SEGMENTS

    return {
        "seo": seo.for_request(request),
        "gtm_id": gtm_id(),
        "google_login": google_login_enabled(),
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
        "plan_state": _plan_state(request),
        "contact_email": settings.CONTACT_EMAIL,
        "maintenance_bypass": getattr(request, "maintenance_bypass", False),
        "guest_account": is_guest_account(getattr(request, "user", None)),
        # Working in a team's workspace, not one's own (apps/accounts/team.py).
        "team_member": getattr(request, "membership", None) is not None,
        "workspaces": _workspaces(request),
    }
