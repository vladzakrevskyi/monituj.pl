"""The legal documents: their pages, their versions and their wording.

Each document has its own version - the date its wording applies from
(settings.LEGAL_VERSIONS, from LEGAL_*_DATE in .env) - so the Privacy policy
can change without a new
Regulamin. Every wording in force is archived (consents.LegalVersion): what
people accepted, and what a buyer got, can be shown word for word later."""

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.site import absolute_url

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
    "backup_days": "liczba dni rotacji kopii zapasowych",
    "hosting_location": "kraj lokalizacji serwerów",
}


PROVIDER_KEYS = ("hosting_provider", "email_provider")


@dataclass(frozen=True)
class Document:
    key: str
    title: str
    template: str
    url_name: str
    # Part of what users accept (at sign-up and again after a change).
    accepted: bool = False


TERMS = "regulamin"
DPA = "umowa_powierzenia"
PRIVACY = "polityka_prywatnosci"
COOKIES = "polityka_cookies"
WITHDRAWAL = "odstapienie_od_umowy"

DOCUMENTS = {
    doc.key: doc
    for doc in (
        Document(TERMS, "Regulamin", "legal/terms.html", "legal:terms", True),
        Document(
            DPA,
            "Umowa powierzenia przetwarzania danych",
            "legal/dpa.html",
            "legal:dpa",
            True,
        ),
        Document(
            PRIVACY,
            "Polityka prywatności",
            "legal/privacy.html",
            "legal:privacy",
            True,
        ),
        Document(COOKIES, "Polityka cookies", "legal/cookies.html", "legal:cookies"),
        Document(
            WITHDRAWAL,
            "Odstąpienie od umowy",
            "legal/withdrawal.html",
            "legal:withdrawal",
        ),
    )
}
ACCEPTED = [key for key, doc in DOCUMENTS.items() if doc.accepted]
# What a paid plan is bought on - in the order a buyer receives them.
CONTRACT = [TERMS, DPA, WITHDRAWAL]


def version(key):
    """The document's version: the ISO date its wording applies from."""
    return settings.LEGAL_VERSIONS[key]


def effective_date(key):
    return date.fromisoformat(version(key))


def in_force(key):
    """A version dated in the future is already shown (so users can read it
    ahead), but accepting it becomes required only from that day."""
    return effective_date(key) <= timezone.localdate()


def effective_date_display(key):
    return date_format(effective_date(key), "j E Y")


def version_display(version):
    """ "2026-10-15" -> "15 października 2026"."""
    return date_format(date.fromisoformat(version), "j E Y")


def legal_context(key=None):
    """The operator's details for the documents - and, for one document,
    the date its wording applies from."""
    entity = getattr(settings, "LEGAL_ENTITY", {})
    context = {}
    for field, label in PLACEHOLDERS.items():
        value = entity.get(field, "")
        # A provider is a company name - an email address put there by
        # mistake would be published as the name.
        if field in PROVIDER_KEYS and "@" in value:
            value = ""
        context[field] = value or format_html(
            '<mark class="legal-todo">[uzupełnij: {}]</mark>', label
        )
    # Optional, no placeholder: the policies mention a CDN only when there is one.
    cdn = entity.get("cdn_provider", "")
    context["cdn_provider"] = "" if "@" in cdn else cdn
    if key:
        context["effective_date"] = effective_date_display(key)
    if not entity.get("email"):
        context["email"] = settings.CONTACT_EMAIL
    if not entity.get("privacy_email"):
        context["privacy_email"] = context["email"]
    context["vat_rate"] = settings.BILLING_VAT_RATE
    return context


def render_body(key):
    """The document's wording as a standalone HTML fragment - title, date
    and text, exactly as the page shows them - for the archive and for the
    copy attached to an order."""
    from apps.accounts.google import enabled as google_login_enabled
    from apps.common.cookies import consent as cookie_consent

    return render_to_string(
        DOCUMENTS[key].template,
        {
            "legal": legal_context(key),
            "legal_base": "legal/_fragment.html",
            # What the site's context processor gives the pages.
            "google_login": google_login_enabled(),
            "cookie_consent": cookie_consent(),
        },
    ).strip()


def _legal_page(key):
    """A document's page. During its notice period (a new version dated
    ahead) it shows the wording in force, from the archive, as if nothing
    changed; the new one opens only from the announcement email
    (?wersja=nowa), saying from when it applies."""

    def view(request):
        context = {"legal": legal_context(key)}
        if not in_force(key):
            from apps.consents.versions import in_force as wording_in_force

            earlier = wording_in_force(key)
            since = effective_date_display(key)
            if earlier is not None and request.GET.get("wersja") != "nowa":
                return render(
                    request,
                    "legal/in_force.html",
                    {
                        "document": DOCUMENTS[key],
                        "html": mark_safe(earlier.html),  # noqa: S308 - our own text
                    },
                )
            context["upcoming"] = {
                "since": since,
                "current_url": request.path if earlier is not None else None,
            }
        return render(request, DOCUMENTS[key].template, context)

    return view


def contract_attachment():
    """The contract documents as one PDF for the order confirmation email -
    the copy a buyer keeps on a durable medium (art. 21 of the consumer
    rights act): unlike the pages, it can't change later. The same wording
    as archived for the order. Returns (filename, bytes, mimetype)."""
    # WeasyPrint needs Pango; imported here so only the worker, which sends
    # the email, loads it.
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    from apps.consents.versions import current
    from apps.consents.versions import in_force as wording_in_force

    # The wording in force - during a notice period the earlier one: the
    # contract is concluded on it.
    parts = [
        mark_safe((wording_in_force(key) or current(key)).html) for key in CONTRACT
    ]
    html = render_to_string(
        "legal/attachment.html",
        {
            "parts": parts,
            "issued": date_format(timezone.localdate(), "j E Y"),
        },
    )
    # Nothing is loaded from outside - no image, stylesheet or file; links
    # stay links, resolved against the site.
    pdf = HTML(
        string=html,
        base_url=absolute_url("/"),
        url_fetcher=URLFetcher(allowed_protocols=()),
    ).write_pdf()
    return ("Monituj-regulamin.pdf", pdf, "application/pdf")


terms = _legal_page(TERMS)
privacy = _legal_page(PRIVACY)
cookies = _legal_page(COOKIES)
dpa = _legal_page(DPA)
withdrawal = _legal_page(WITHDRAWAL)
