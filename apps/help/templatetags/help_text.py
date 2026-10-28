"""The help articles' markup: **bold** and [[slug]] / [[slug|text]] links to
other articles. Everything else is escaped."""

import re

from django import template
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.help.articles import BY_SLUG

register = template.Library()

_LINK = re.compile(r"\[\[([a-z0-9-]+)(?:\|([^\]]+))?\]\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _link(match):
    article = BY_SLUG[match.group(1)]
    text = match.group(2) or article.title
    url = reverse("help:article", args=[article.slug])
    return f'<a href="{url}">{text}</a>'


@register.filter
def help_text(value):
    html = escape(value)
    html = _LINK.sub(_link, html)
    html = _BOLD.sub(r"<strong>\1</strong>", html)
    return mark_safe(html)


@register.filter
def help_plain(value):
    """For <meta> and titles: the text without the markup."""
    value = _LINK.sub(lambda m: m.group(2) or BY_SLUG[m.group(1)].title, value)
    return value.replace("**", "")
