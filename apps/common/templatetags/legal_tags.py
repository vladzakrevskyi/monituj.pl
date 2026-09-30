"""{% upcoming_documents as upcoming %} - the accepted documents with a new
version announced ahead (a notice period is running), for the note under
the consent checkboxes: accepting covers the version in force; the new one
is asked for on its day (consents.services)."""

from django import template
from django.urls import reverse

from apps.common import legal

register = template.Library()


@register.simple_tag
def upcoming_documents():
    from apps.consents.versions import in_force

    return [
        {
            "title": legal.DOCUMENTS[key].title,
            "url": reverse(legal.DOCUMENTS[key].url_name) + "?wersja=nowa",
            "since": legal.effective_date_display(key),
        }
        for key in legal.ACCEPTED
        if not legal.in_force(key) and in_force(key) is not None
    ]
