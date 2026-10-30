from django import template

from apps.common.formatting import days_text, days_until, format_date, format_datetime

register = template.Library()


@register.filter
def dt(value):
    return format_datetime(value)


@register.filter
def d(value):
    return format_date(value)


@register.filter
def due(value):
    """A deadline as people say it: "za 4 dni", "dziś", "3 dni temu"."""
    return days_text(days_until(value))


@register.filter
def is_past(value):
    days = days_until(value)
    return days is not None and days < 0
