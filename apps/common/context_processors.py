from django.conf import settings


def site(request):
    return {
        "contact_email": settings.CONTACT_EMAIL,
        "maintenance_bypass": getattr(request, "maintenance_bypass", False),
    }
