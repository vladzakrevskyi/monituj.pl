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
