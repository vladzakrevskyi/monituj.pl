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
