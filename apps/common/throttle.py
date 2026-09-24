"""Simple rate limits stored in the database, so they hold across every
web process. Limits are generous: they only stop scripts and abuse, never
someone using Monituj normally."""

from datetime import timedelta

from django.utils import timezone

from apps.common.exceptions import RateLimitedAppError
from apps.common.models import ThrottleEvent
from apps.common.security import get_client_ip, hash_ip

TOO_MANY_MESSAGE = "Zbyt wiele prób w krótkim czasie. Spróbuj ponownie za kilka minut."


def ip_key(prefix, django_request):
    return f"{prefix}:{hash_ip(get_client_ip(django_request))}"


def count(key, window):
    since = timezone.now() - window
    ThrottleEvent.objects.filter(key=key, created_at__lt=since).delete()
    return ThrottleEvent.objects.filter(key=key, created_at__gte=since).count()


def is_limited(key, limit, window):
    return count(key, window) >= limit


def record(key):
    ThrottleEvent.objects.create(key=key)


def clear(key):
    ThrottleEvent.objects.filter(key=key).delete()


def consume(key, limit, window, message=TOO_MANY_MESSAGE, code="RATE_LIMITED"):
    """Counts one action and refuses it once the limit is reached."""
    if is_limited(key, limit, window):
        raise RateLimitedAppError(message, code=code)
    record(key)


MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
