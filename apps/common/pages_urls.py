from django.urls import path

from apps.common import pages

app_name = "pages"

urlpatterns = [
    path("jak-to-dziala/", pages.how_it_works, name="how-it-works"),
    path("funkcje/", pages.features, name="features"),
    path("dla-kogo/", pages.for_whom, name="for-whom"),
    path("bezpieczenstwo/", pages.security, name="security"),
    path("cennik/", pages.pricing, name="pricing"),
    path("faq/", pages.faq, name="faq"),
    path("kontakt/", pages.contact, name="contact"),
    path("demo/", pages.demo, name="demo"),
]
