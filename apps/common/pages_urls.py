from django.urls import path
from django.views.generic import RedirectView

from apps.common import pages
from apps.contact.views import contact

app_name = "pages"

# Short address for the Instagram profile: Instagram shows the link in full,
# so the campaign tags live here. Temporary, so the target can still change.
INSTAGRAM_BIO_TARGET = "/?utm_source=instagram&utm_medium=social&utm_campaign=bio"

urlpatterns = [
    path("ig/", RedirectView.as_view(url=INSTAGRAM_BIO_TARGET), name="instagram-bio"),
    path("jak-to-dziala/", pages.how_it_works, name="how-it-works"),
    path("film/", pages.film, name="film"),
    path("funkcje/", pages.features, name="features"),
    path("dla-kogo/", pages.for_whom, name="for-whom"),
    path("dla-kogo/<slug:slug>/", pages.segment, name="segment"),
    path("poradnik/jak-zbierac-dokumenty-od-klientow/", pages.guide, name="guide"),
    path("poradnik/dokumenty-spoza-ksef/", pages.outside_ksef, name="outside-ksef"),
    path(
        "poradnik/pytania-do-klienta/", pages.client_questions, name="client-questions"
    ),
    path("szablony/", pages.templates_library, name="templates"),
    path("szablony/<slug:slug>/", pages.template_page, name="template"),
    path("bezpieczenstwo/", pages.security, name="security"),
    path("cennik/", pages.pricing, name="pricing"),
    path("porownanie/email-whatsapp-dysk/", pages.comparison, name="comparison"),
    path("kalkulator-czasu/", pages.calculator, name="calculator"),
    path("faq/", pages.faq, name="faq"),
    path("kontakt/", contact, name="contact"),
    path("demo/", pages.demo, name="demo"),
]
