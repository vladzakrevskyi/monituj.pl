from django.utils import timezone
from django.utils.dateformat import format as date_format

DATETIME_FORMAT = "j E Y H:i"
DATE_FORMAT = "j E Y"


def format_datetime(value):
    """25 września 2026 23:59, in the site's local time zone."""
    if value is None:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, DATETIME_FORMAT)


def format_date(value):
    if value is None:
        return ""
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, DATE_FORMAT)


def days_text(days):
    """ "3 dni temu", "dziś", "za 1 dzień" - or "" for None."""
    if days is None:
        return ""
    if days == 0:
        return "dziś"
    count = abs(days)
    unit = "dzień" if count == 1 else "dni"
    return f"{count} {unit} temu" if days < 0 else f"za {count} {unit}"


def days_until(value, today=None):
    """Whole days from today to a date or datetime - negative once past."""
    if value is None:
        return None
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    if hasattr(value, "date"):
        value = value.date()
    return (value - (today or timezone.localdate())).days
