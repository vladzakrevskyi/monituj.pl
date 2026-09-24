from django.conf import settings


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL.rstrip('/')}{path}"
