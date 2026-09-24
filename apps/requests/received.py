"""Requests someone sent *to* a person: shown in their panel (Otrzymane)
when they have an account with that verified address, and on the
recipient's page (/moje-prosby/<token>/) when they don't."""

from apps.requests.models import Request
from apps.requests.services import RequestStatus, compute_status, with_stats

SESSION_KEY = "verified_recipient_emails"
FINISHED = {RequestStatus.COMPLETE, RequestStatus.CLOSED}
VIEWS = {
    "otwarte": "Do uzupełnienia",
    "zakonczone": "Zakończone",
    "wszystkie": "Wszystkie",
}


def received_requests(email):
    requests = list(
        with_stats(
            Request.objects.filter(
                client__email__iexact=email, awaiting_confirmation=False
            ).select_related("created_by", "client")
        ).order_by("-created_at")
    )
    for request_obj in requests:
        status = compute_status(request_obj)
        request_obj.status_label = status.label
        request_obj.status_code = status.value
        request_obj.is_finished = status in FINISHED
    return requests


def open_count(email):
    return sum(1 for r in received_requests(email) if not r.is_finished)


def filtered(requests, view):
    """Returns (rows, tabs) for the Do uzupełnienia / Zakończone tabs."""
    view = view if view in VIEWS else "otwarte"
    groups = {
        "otwarte": [r for r in requests if not r.is_finished],
        "zakonczone": [r for r in requests if r.is_finished],
        "wszystkie": requests,
    }
    tabs = [
        {"key": key, "label": label, "count": len(groups[key]), "active": key == view}
        for key, label in VIEWS.items()
    ]
    return groups[view], tabs


def account_email(user):
    """The address whose received requests a logged-in user may see - only
    once they have proved they own it."""
    if user.is_authenticated and user.email_verified_at is not None:
        return user.email
    return None


def mark_recipient_verified(django_request, email):
    """Opening the recipient's page proves they read that inbox."""
    emails = set(django_request.session.get(SESSION_KEY, []))
    emails.add(email.lower())
    django_request.session[SESSION_KEY] = sorted(emails)


def is_verified_recipient(django_request, email):
    email = email.lower()
    user_email = account_email(django_request.user)
    if user_email and user_email.lower() == email:
        return True
    return email in django_request.session.get(SESSION_KEY, [])
