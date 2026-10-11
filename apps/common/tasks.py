from celery import shared_task
from django.utils import timezone

from apps.common.models import ThrottleEvent
from apps.common.throttle import DAY


@shared_task
def delete_old_throttle_events():
    """No limit looks back further than a day."""
    deleted, _ = ThrottleEvent.objects.filter(
        created_at__lt=timezone.now() - DAY
    ).delete()
    return deleted


@shared_task
def send_security_digest_fallback():
    """The daily security report normally comes from the server's cron with
    the server's own part (deploy/security/daily-report.sh). If it hasn't
    by now - not installed, or something stopped it - the site's part goes
    out anyway and says the server's is missing."""
    from django.conf import settings

    from apps.common import security_digest

    if not settings.SECURITY_ALERTS or security_digest.sent_recently():
        return False
    security_digest.send()
    return True
