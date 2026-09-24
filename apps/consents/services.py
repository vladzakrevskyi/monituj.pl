from django.utils import timezone

from apps.common import legal
from apps.common.security import get_client_ip
from apps.consents.models import LegalAcceptance, LegalDocument

# Accepted together, always: the Terms with the data processing agreement,
# and the Privacy policy (read - the account runs on the contract, not on
# consent).
ALL_DOCUMENTS = [LegalDocument.TERMS, LegalDocument.DPA, LegalDocument.PRIVACY]


def record_acceptance(user, method, request=None):
    """Stores who accepted which version, when, from where. Also keeps the
    quick timestamps on the account up to date."""
    now = timezone.now()
    version = legal.version()
    ip_address = (get_client_ip(request) or None) if request is not None else None
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""
    LegalAcceptance.objects.bulk_create(
        [
            LegalAcceptance(
                user=user,
                document=document,
                version=version,
                method=method,
                accepted_at=now,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            for document in ALL_DOCUMENTS
        ]
    )
    user.terms_accepted_at = now
    user.privacy_policy_accepted_at = now
    user.save(update_fields=["terms_accepted_at", "privacy_policy_accepted_at"])


def has_accepted_current(user):
    return LegalAcceptance.objects.filter(
        user=user, document=LegalDocument.TERMS, version=legal.version()
    ).exists()


def needs_acceptance(user):
    """True when the documents in force are newer than what this person
    accepted - including accounts from before versions were recorded."""
    from apps.demo.models import is_demo_user

    if not legal.in_force():
        return False
    if not user.is_authenticated or not user.is_active or is_demo_user(user):
        return False
    return not has_accepted_current(user)
