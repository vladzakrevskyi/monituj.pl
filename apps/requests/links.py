"""Permanent links that replace a login: the guest sender's panel link and
the recipient's "all my requests" page."""

from urllib.parse import urlencode

from django.urls import reverse

from apps.common.site import absolute_url
from apps.common.timezones import browser_timezone
from apps.requests.models import RecipientAccess


def guest_panel_url(user, next_path=None):
    """The one link a passwordless sender uses to open their panel - always
    the same for the account. Optionally lands on a specific page."""
    url = absolute_url(reverse("accounts:guest-access", args=[user.guest_access.token]))
    if next_path:
        url += "?" + urlencode({"next": next_path})
    return url


def guest_email_url(user, next_path=None):
    """A 14-day login link for everyday emails - an old forwarded email
    must not open the panel for good (the permanent link is sent only in
    the "Twój panel" email)."""
    from apps.accounts.services import GuestAccessService

    url = absolute_url(
        reverse(
            "accounts:guest-email-access",
            args=[GuestAccessService.email_link_token(user)],
        )
    )
    if next_path:
        url += "?" + urlencode({"next": next_path})
    return url


def owner_link(user, path):
    """Where an email to a request's sender should point: straight into the
    panel for regular accounts, through a 14-day login link for guests."""
    if hasattr(user, "guest_access"):
        return guest_email_url(user, path)
    return absolute_url(path)


def recipient_portal_url(email):
    access, _ = RecipientAccess.objects.get_or_create(email=email.strip().lower())
    return absolute_url(reverse("public:recipient-portal", args=[access.token]))


def remember_recipient_timezone(email, django_request):
    """Called when a recipient opens one of their pages: from then on their
    reminders follow their own clock."""
    detected = browser_timezone(django_request)
    if not detected:
        return
    access, _ = RecipientAccess.objects.get_or_create(email=email.strip().lower())
    if access.timezone != detected:
        access.timezone = detected
        access.save(update_fields=["timezone"])
