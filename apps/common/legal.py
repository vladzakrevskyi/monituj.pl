from django.conf import settings
from django.shortcuts import render
from django.utils.html import format_html

PLACEHOLDERS = {
    "name": "nazwa firmy",
    "address": "adres siedziby",
    "nip": "NIP",
    "regon": "REGON",
    "register": "wpis do KRS lub CEIDG",
    "email": "email kontaktowy",
    "privacy_email": "email w sprawach danych osobowych",
    "hosting_provider": "dostawca hostingu",
    "email_provider": "dostawca poczty email",
    "effective_date": "data wejścia w życie",
    "backup_days": "liczba dni rotacji kopii zapasowych",
    "hosting_location": "kraj lokalizacji serwerów",
}


def legal_context():
    entity = getattr(settings, "LEGAL_ENTITY", {})
    context = {}
    for key, label in PLACEHOLDERS.items():
        value = entity.get(key, "")
        context[key] = value or format_html(
            '<mark class="legal-todo">[uzupełnij: {}]</mark>', label
        )
    if not entity.get("email"):
        context["email"] = settings.CONTACT_EMAIL
    if not entity.get("privacy_email"):
        context["privacy_email"] = context["email"]
    return context


def _legal_page(template):
    def view(request):
        return render(request, template, {"legal": legal_context()})

    return view


terms = _legal_page("legal/terms.html")
privacy = _legal_page("legal/privacy.html")
cookies = _legal_page("legal/cookies.html")
dpa = _legal_page("legal/dpa.html")
