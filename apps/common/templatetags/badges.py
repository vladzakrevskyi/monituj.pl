from django import template

register = template.Library()

# One meaning, one colour, on every page: orange - waiting for the client,
# black - your turn, green - done, red - late or rejected, grey - nothing to
# do. A document not sent yet is no alarm, so it's grey.
STATUS_BADGE_CLASSES = {
    "aktywny": "badge--progress",
    "brak_dokumentow": "badge--progress",
    "wszystko_dostarczone": "badge--complete",
    "nieaktywny": "badge--neutral",
    "w_trakcie": "badge--progress",
    "kompletny": "badge--complete",
    "po_terminie": "badge--overdue",
    "brak": "badge--neutral",
    "dostarczony": "badge--action",
    "zaakceptowany": "badge--complete",
    "odrzucony": "badge--overdue",
    "nie_dotyczy": "badge--neutral",
    "zamkniety": "badge--neutral",
    "niepotwierdzony": "badge--neutral",
}


@register.filter
def badge_class(status_code):
    return STATUS_BADGE_CLASSES.get(status_code, "badge--neutral")


# A question not answered yet, or asked again, waits for the client.
QUESTION_WAITING = {"brak", "odrzucony"}


@register.filter
def item_badge_class(item):
    if item.is_question and item.status in QUESTION_WAITING:
        return "badge--progress"
    return badge_class(item.status)
