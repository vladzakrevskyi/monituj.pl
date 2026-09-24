"""Time zones of the people using Monituj.

The browser reports its zone in a small "tz" cookie (static/js/timezone.js).
Logged-in users get it stored on their account and see dates in it; for a
request's sender and recipient it decides when reminders go out."""

from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from django.conf import settings
from django.utils import timezone

COOKIE_NAME = "tz"


@lru_cache(maxsize=1)
def _known_zones():
    return frozenset(available_timezones())


def valid_timezone(name):
    """The name if it is a real IANA zone, otherwise None."""
    name = (name or "").strip()
    return name if name in _known_zones() else None


def zone(name):
    return ZoneInfo(valid_timezone(name) or settings.TIME_ZONE)


def browser_timezone(request):
    return valid_timezone(request.COOKIES.get(COOKIE_NAME))


class TimezoneMiddleware:
    """Keeps a logged-in user's zone up to date and shows every page in the
    viewer's own zone (the account's, or the browser's for visitors)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        detected = browser_timezone(request)
        user = getattr(request, "user", None)
        active = detected
        if user is not None and user.is_authenticated:
            if detected and detected != user.timezone:
                user.timezone = detected
                user.save(update_fields=["timezone"])
            active = valid_timezone(user.timezone)
        if active:
            timezone.activate(ZoneInfo(active))
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
