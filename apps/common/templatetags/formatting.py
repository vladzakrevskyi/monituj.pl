from django import template

from apps.common.formatting import format_date, format_datetime

register = template.Library()


@register.filter
def dt(value):
    return format_datetime(value)


@register.filter
def d(value):
    return format_date(value)
