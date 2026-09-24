from django import template

register = template.Library()

STATUS_BADGE_CLASSES = {
    "aktywny": "badge--progress",
    "brak_dokumentow": "badge--missing",
    "wszystko_dostarczone": "badge--complete",
    "nieaktywny": "badge--neutral",
    "w_trakcie": "badge--progress",
    "kompletny": "badge--complete",
    "po_terminie": "badge--overdue",
    "brak": "badge--missing",
    "dostarczony": "badge--progress",
    "zaakceptowany": "badge--complete",
    "odrzucony": "badge--overdue",
    "zamkniety": "badge--neutral",
    "niepotwierdzony": "badge--neutral",
}


@register.filter
def badge_class(status_code):
    return STATUS_BADGE_CLASSES.get(status_code, "badge--neutral")
