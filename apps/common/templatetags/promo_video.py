from django import template

from apps.common import promo_video as film

register = template.Library()


@register.inclusion_tag("pages/_promo_video.html")
def promo_video(chapters=True):
    """{% promo_video %} - the film with its chapter buttons;
    chapters=False for the copy in the hero dialog."""
    return {
        "film": film,
        "chapters": [
            {"number": number, "label": label, "wide": wide, "tall": tall}
            for number, (label, wide, tall) in enumerate(film.CHAPTERS, start=1)
        ]
        if chapters
        else [],
    }


@register.simple_tag
def promo_video_minutes():
    return film.minutes_label()
