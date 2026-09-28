"""Official firm details for a Polish NIP.

lookup() asks GUS (REGON - every firm, VAT payer or not) for the name and
address, and the Ministry of Finance VAT register ("Biała lista",
wl-api.mf.gov.pl) for the VAT status - or for everything, when GUS can't be
asked. Registers that don't answer never block anyone: the NIP checksum is
checked anyway, and the buyer can then type the details in."""

import logging
import re

import requests
from django.utils import timezone

logger = logging.getLogger("monituj")

URL = "https://wl-api.mf.gov.pl/api/search/nip/{nip}"
TIMEOUT = 8
ROMAN = re.compile(r"^[IVX]{2,4}$")
ADDRESS = re.compile(r"^(?P<street>.+),\s*(?P<post_code>\d{2}-\d{3})\s+(?P<city>.+)$")


class InvalidNip(Exception):
    """The register says the NIP doesn't exist or is malformed."""


class FirmClosed(InvalidNip):
    """GUS says the firm has ended its business."""


def _pretty(text):
    """'ŚWIĘTOKRZYSKA 12' -> 'Świętokrzyska 12' (numbers and Roman numerals
    as they are); names of firms stay as registered."""
    return " ".join(
        word
        if any(ch.isdigit() for ch in word) or ROMAN.match(word)
        else word.capitalize()
        for word in text.split()
    )


def mf_lookup(nip):
    """{'name', 'status', 'street', 'post_code', 'city'} from the VAT
    register, None when the NIP is not listed there (e.g. a sole trader
    outside VAT) or the register can't be asked right now. Raises InvalidNip."""
    try:
        response = requests.request(
            "GET",
            URL.format(nip=nip),
            params={"date": timezone.localdate().isoformat()},
            timeout=TIMEOUT,
        )
        data = response.json()
    except requests.RequestException, ValueError:
        logger.warning("MF register unavailable for NIP lookup")
        return None
    if response.status_code == 400 and str(data.get("code", "")).startswith("WL-11"):
        raise InvalidNip(data.get("message") or "Nieprawidłowy NIP.")
    if response.status_code != 200:
        logger.warning("MF register answered %s", response.status_code)
        return None
    subject = (data.get("result") or {}).get("subject")
    if not subject:
        return None
    found = {
        "name": subject.get("name") or "",
        "status": subject.get("statusVat") or "",
    }
    address = subject.get("workingAddress") or subject.get("residenceAddress") or ""
    match = ADDRESS.match(address.strip())
    if match:
        found.update(
            street=_pretty(match["street"]),
            post_code=match["post_code"],
            city=_pretty(match["city"]),
        )
    return found


FIELDS = ("name", "street", "post_code", "city")


def lookup(nip):
    """{'name', 'street', 'post_code', 'city', 'status', 'source'} for a
    Polish NIP - each detail from GUS, or from the Ministry of Finance VAT
    register when GUS lacks it; a detail no register has is "". None when
    no register knows the firm (or none answers).
    Raises InvalidNip (FirmClosed for a firm that ended its business)."""
    from apps.billing import gus

    found = None
    try:
        found = gus.lookup(nip)
    except gus.FirmClosed as exc:
        raise FirmClosed(str(exc)) from exc
    except gus.GusError as exc:
        logger.warning("GUS lookup unavailable: %s", exc)
    vat = mf_lookup(nip) or {}
    if not found and not vat:
        return None
    merged = {
        field: ((found or {}).get(field) or vat.get(field) or "").strip()
        for field in FIELDS
    }
    merged.update(source="GUS" if found else "MF", status=vat.get("status", ""))
    return merged
