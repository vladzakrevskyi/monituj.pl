from datetime import datetime

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.utils.formats import date_format
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


def version():
    """The documents' version: their effective date (LEGAL_EFFECTIVE_DATE,
    as 2026-10-01 or 01.10.2026). Empty = not published yet, nothing to
    accept."""
    return (getattr(settings, "LEGAL_ENTITY", {}).get("effective_date") or "").strip()


def effective_date():
    raw = version()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):  # 2026-10-01 or 01.10.2026
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def in_force():
    """A version dated in the future is already shown (so users can read it
    ahead), but accepting it becomes required only from that day."""
    if not version():
        return False
    starts = effective_date()
    return starts is None or starts <= timezone.localdate()


def effective_date_display():
    starts = effective_date()
    return date_format(starts, "j E Y") if starts else version()


def legal_context():
    entity = getattr(settings, "LEGAL_ENTITY", {})
    context = {}
    for key, label in PLACEHOLDERS.items():
        value = entity.get(key, "")
        context[key] = value or format_html(
            '<mark class="legal-todo">[uzupełnij: {}]</mark>', label
        )
    if version():
        context["effective_date"] = effective_date_display()
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
