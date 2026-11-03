from django import template
from django.templatetags.static import static

from apps.common import promo_video as film

register = template.Library()


@register.inclusion_tag("pages/_promo_video.html")
def promo_video(chapters=True, deep_link=False):
    """{% promo_video %} - the film with its chapter buttons;
    chapters=False for the copy in the hero dialog, deep_link=True on /film/,
    where ?t=29 opens it at that second."""
    return {
        "film": film,
        "wide": film.stable_url(film.WIDE),
        "wide_poster": film.stable_url(film.WIDE_POSTER),
        "tall": film.stable_url(film.TALL),
        "tall_poster": film.stable_url(film.TALL_POSTER),
        "deep_link": deep_link,
        "chapters": film.chapters() if chapters else [],
    }


@register.simple_tag
def promo_video_minutes():
    return film.minutes_label()


@register.simple_tag
def promo_video_clock():
    """The length as a player shows it: 2:10."""
    return film.clock(film.SECONDS)


@register.simple_tag
def promo_video_chapters():
    return film.chapters()


@register.simple_tag
def promo_video_thumb():
    return static(film.THUMB)
