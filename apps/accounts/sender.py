"""How a sender appears to the people they ask for documents.

The name is chosen by the sender, so on its own it proves nothing - anyone
could call themselves a tax office or a bank. So recipients always see it
together with the sender's confirmed email address, plus the firm's name
and NIP if the sender chose to show them (Ustawienia); names that mimic
public institutions, banks or Monituj itself are refused up front.

The firm line needs more than a NIP typed in - anyone could type a known
firm's. It is offered only for a firm the account pays for: the subscription
is paid and an invoice to that NIP was issued (in KSeF the firm sees it)."""

import re
import unicodedata

from django.core.exceptions import ValidationError

DECEPTIVE_MESSAGE = (
    "Ta nazwa może wprowadzać odbiorców w błąd - przypomina instytucję "
    "publiczną, bank albo Monituj. Użyj nazwy swojej firmy albo imienia i "
    "nazwiska."
)
# Matched as whole words in the name, without Polish letters and case.
DECEPTIVE = [
    r"urzad(u|em)? skarbow\w*",
    r"skarbowk\w*",
    r"krajow\w* administracj\w* skarbow\w*",
    r"kas",
    r"izb\w* administracji skarbowej",
    r"zus",
    r"zaklad\w* ubezpieczen spolecznych",
    r"krus",
    r"nfz",
    r"gus",
    r"ministerstw\w*",
    r"ministr\w*",
    # Declined forms only - "urządzenia" (devices) is a fine firm name.
    r"rzad(u|owi|em|zie|owy|owa|owe)?",
    r"urzad",
    r"urzed(u|owi|em|zie|y|ow|ach)",
    r"gov(\.pl)?",
    r"policj\w*",
    r"prokuratur\w*",
    r"sad(u|owi|em|zie|y|ow)?",
    r"komornik\w*",
    r"straz\w*",
    r"bank(u|owi|iem|i|ow)?",
    r"pko",
    r"pekao",
    r"mbank",
    r"santander",
    r"millennium",
    r"alior",
    r"ing",
    r"bnp paribas",
    r"credit agricole",
    r"citi\w*",
    r"revolut",
    r"monituj\w*",
]
_DECEPTIVE_RE = re.compile(r"\b(" + "|".join(DECEPTIVE) + r")\b")


def _plain(value):
    """'Urząd Skarbowy' -> 'urzad skarbowy' (no Polish letters, lower case)."""
    value = value.replace("ł", "l").replace("Ł", "L")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def is_deceptive(name):
    return bool(_DECEPTIVE_RE.search(_plain(name or "")))


def validate_sender_name(name):
    if is_deceptive(name):
        raise ValidationError(DECEPTIVE_MESSAGE, code="deceptive_name")


def paying_firm(user):
    """'NAZWA Z REJESTRU, NIP 5213017228' when the account's paid plan is
    invoiced to a firm whose name came from the register, otherwise ''."""
    from apps.billing.models import (
        BillingAccount,
        BillingProfile,
        VatInvoice,
        VatInvoiceStatus,
    )
    from apps.billing.services import is_subscribed

    profile = BillingProfile.objects.filter(user=user).first()
    if profile is None or not profile.is_company or not profile.registry_source:
        return ""
    account = BillingAccount.objects.filter(user=user).first()
    if account is None or not is_subscribed(account):
        return ""
    invoiced = VatInvoice.objects.filter(
        user=user,
        status=VatInvoiceStatus.ISSUED,
        client__client_tax_code=profile.tax_id,
    ).exists()
    return f"{profile.company_name}, NIP {profile.tax_id}" if invoiced else ""


def sender_context(user):
    """What emails and pages show about the sender of a request."""
    name = user.display_name or ""
    firm = paying_firm(user)
    return {
        # Never empty: the address stands in for a missing name.
        "sender_name": name or user.email,
        "sender_email": user.email,
        # "Biuro X (jan@biuro-x.pl)" - the confirmed address with the name.
        "sender_from": f"{name} ({user.email})" if name else user.email,
        # The firm's name and NIP - only with the sender's consent.
        "sender_firm": firm if user.show_paying_firm else "",
    }


def suggested_name(user):
    """A first guess for the name to show recipients: the firm from the
    invoice details, if any."""
    from apps.billing.models import BillingProfile

    profile = BillingProfile.objects.filter(user=user).first()
    if profile is None:
        return ""
    return profile.company_name if profile.is_company else profile.display_name
