from django.contrib import admin
from django.urls import include, path

from apps.common import seo_views
from apps.common.pages import landing
from apps.common.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing, name="landing"),
    path("robots.txt", seo_views.robots_txt, name="robots-txt"),
    path("sitemap.xml", seo_views.sitemap_xml, name="sitemap-xml"),
    path("llms.txt", seo_views.llms_txt, name="llms-txt"),
    path("llms-full.txt", seo_views.llms_full_txt, name="llms-full-txt"),
    path("site.webmanifest", seo_views.web_manifest, name="web-manifest"),
    path("favicon.ico", seo_views.favicon, name="favicon"),
    path("apple-touch-icon.png", seo_views.apple_touch_icon),
    path("apple-touch-icon-precomposed.png", seo_views.apple_touch_icon),
    path("api/health/", health_check, name="health-check"),
    path("api/", include("apps.clients.api_urls")),
    path("api/", include("apps.requests.api_urls")),
    path("api/", include("apps.documents.api_urls")),
    path("api/", include("apps.reminders.api_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.clients.urls")),
    path("", include("apps.requests.urls")),
    path("", include("apps.requests.public_urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.consents.urls")),
    path("", include("apps.common.legal_urls")),
    path("", include("apps.common.pages_urls")),
    path("", include("apps.demo.urls")),
]
