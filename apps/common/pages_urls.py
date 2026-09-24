from django.urls import path

from apps.common import pages
from apps.contact.views import contact

app_name = "pages"

urlpatterns = [
    path("jak-to-dziala/", pages.how_it_works, name="how-it-works"),
    path("funkcje/", pages.features, name="features"),
    path("dla-kogo/", pages.for_whom, name="for-whom"),
    path("dla-kogo/<slug:slug>/", pages.segment, name="segment"),
    path("poradnik/jak-zbierac-dokumenty-od-klientow/", pages.guide, name="guide"),
    path("bezpieczenstwo/", pages.security, name="security"),
    path("cennik/", pages.pricing, name="pricing"),
    path("faq/", pages.faq, name="faq"),
    path("kontakt/", contact, name="contact"),
    path("demo/", pages.demo, name="demo"),
]
