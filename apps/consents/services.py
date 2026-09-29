from django.utils import timezone

from apps.common import legal
from apps.common.security import get_client_ip
from apps.consents.models import LegalAcceptance
from apps.consents.versions import current

# Accepted together, always: the Terms with the data processing agreement,
# and the Privacy policy (read - the account runs on the contract, not on
# consent). Each is recorded with its own version and exact wording.
ALL_DOCUMENTS = legal.ACCEPTED


def record_acceptance(user, method, request=None):
    """Stores who accepted which version of each document - and its exact
    wording - when, from where. Also keeps the quick timestamps on the
    account up to date."""
    now = timezone.now()
    ip_address = (get_client_ip(request) or None) if request is not None else None
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""
    rows = []
    for document in ALL_DOCUMENTS:
        wording = current(document)
        rows.append(
            LegalAcceptance(
                user=user,
                document=document,
                version=wording.version,
                wording=wording,
                method=method,
                accepted_at=now,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
    LegalAcceptance.objects.bulk_create(rows)
    user.terms_accepted_at = now
    user.privacy_policy_accepted_at = now
    user.save(update_fields=["terms_accepted_at", "privacy_policy_accepted_at"])


def to_accept(user):
    """The documents whose version in force this person hasn't accepted yet -
    including accounts from before versions were recorded."""
    accepted = set(
        LegalAcceptance.objects.filter(user=user).values_list("document", "version")
    )
    return [
        key
        for key in ALL_DOCUMENTS
        if legal.in_force(key) and (key, legal.version(key)) not in accepted
    ]


def needs_acceptance(user):
    """True when a document in force is newer than what this person
    accepted."""
    from apps.demo.models import is_demo_user

    if not user.is_authenticated or not user.is_active or is_demo_user(user):
        return False
    return bool(to_accept(user))
