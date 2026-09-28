"""How a sender appears to the people they ask for documents.

The name is chosen by the sender, so on its own it proves nothing - anyone
could call themselves a tax office or a bank. So recipients always see it
together with the sender's confirmed email address, plus a "verified firm"
line when the account's invoice details were checked in GUS or the VAT
register; and names that mimic public institutions, banks or Monituj itself
are refused up front."""

import re
import unicodedata

from django.core.exceptions import ValidationError

DECEPTIVE_MESSAGE = (
    "Ta nazwa może wprowadzać odbiorców w błąd – przypomina instytucję "
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


def verified_firm(user):
    """'NAZWA Z REJESTRU, NIP 5213017228' when the account's invoice details
    are a firm checked in GUS or the VAT register, otherwise ''."""
    from apps.billing.models import BillingProfile

    profile = BillingProfile.objects.filter(user=user).first()
    if profile is None or not profile.is_company or not profile.registry_source:
        return ""
    return f"{profile.company_name}, NIP {profile.tax_id}"


def sender_context(user):
    """What emails and pages show about the sender of a request."""
    name = user.display_name or ""
    return {
        # Never empty: the address stands in for a missing name.
        "sender_name": name or user.email,
        "sender_email": user.email,
        # "Biuro X (jan@biuro-x.pl)" - the confirmed address with the name.
        "sender_from": f"{name} ({user.email})" if name else user.email,
        "sender_firm": verified_firm(user),
    }


def suggested_name(user):
    """A first guess for the name to show recipients: the firm from the
    invoice details, if any."""
    from apps.billing.models import BillingProfile

    profile = BillingProfile.objects.filter(user=user).first()
    if profile is None:
        return ""
    return profile.company_name if profile.is_company else profile.display_name
