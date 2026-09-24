from django.contrib import admin
from django.urls import include, path

from apps.common.pages import landing
from apps.common.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing, name="landing"),
    path("api/health/", health_check, name="health-check"),
    path("api/", include("apps.clients.api_urls")),
    path("api/", include("apps.requests.api_urls")),
    path("api/", include("apps.documents.api_urls")),
    path("api/", include("apps.reminders.api_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.clients.urls")),
    path("", include("apps.requests.urls")),
    path("", include("apps.requests.public_urls")),
    path("", include("apps.common.legal_urls")),
    path("", include("apps.common.pages_urls")),
    path("", include("apps.demo.urls")),
]
