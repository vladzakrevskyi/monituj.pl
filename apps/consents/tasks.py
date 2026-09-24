from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.consents.models import CookieConsent

# Long enough to prove a consent (valid 12 months) for as long as a claim
# about it could still be raised.
COOKIE_CONSENT_RETENTION = timedelta(days=3 * 365)


@shared_task
def delete_old_cookie_consents():
    cutoff = timezone.now() - COOKIE_CONSENT_RETENTION
    return CookieConsent.objects.filter(created_at__lt=cutoff).delete()[0]
