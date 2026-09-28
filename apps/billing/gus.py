"""Firm details by NIP from the GUS REGON database (API BIR 1.1).

Unlike the VAT register it knows every firm - sole traders and companies
outside VAT too - so an invoice never depends on the buyer typing their
own address. SOAP 1.2 over HTTPS: log in with the key (Zaloguj) for a
session id, then search by NIP (DaneSzukajPodmioty). The answer is MTOM:
the SOAP envelope sits inside a multipart body."""

import logging
import re
import xml.etree.ElementTree as ET

import requests
from django.conf import settings

logger = logging.getLogger("monituj")

URLS = {
    "test": "https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc",
    "production": "https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc",
}
# GUS's published key for its test environment (anonymised data).
TEST_KEY = "abcde12345abcde12345"
ACTION = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/"
TIMEOUT = 10
ENVELOPE = re.compile(r"<s:Envelope.*</s:Envelope>", re.S)
RESULT = "{http://CIS/BIR/PUBL/2014/07}"


class GusError(Exception):
    """GUS can't be asked right now (no key, network, a broken answer)."""


class FirmClosed(Exception):
    """The firm has ended its business."""


def enabled():
    return settings.GUS_MODE == "test" or bool(settings.GUS_API_KEY)


def _key():
    return TEST_KEY if settings.GUS_MODE == "test" else settings.GUS_API_KEY


def _call(action, body, sid=None):
    url = URLS[settings.GUS_MODE]
    envelope = (
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:ns="http://CIS/BIR/PUBL/2014/07" '
        'xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">'
        '<soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">'
        f"<wsa:To>{url}</wsa:To><wsa:Action>{ACTION}{action}</wsa:Action>"
        f"</soap:Header><soap:Body>{body}</soap:Body></soap:Envelope>"
    )
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    if sid:
        headers["sid"] = sid
    try:
        response = requests.request(
            "POST", url, data=envelope.encode(), headers=headers, timeout=TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GusError(str(exc)) from exc
    match = ENVELOPE.search(response.content.decode("utf-8", "replace"))
    if not match:
        raise GusError("no SOAP envelope in the answer")
    try:
        result = ET.fromstring(match.group(0)).find(f".//{RESULT}{action}Result")
    except ET.ParseError as exc:
        raise GusError("broken SOAP answer") from exc
    return (result.text or "") if result is not None else ""


def _text(element, name):
    found = element.find(name)
    return (found.text or "").strip() if found is not None else ""


def lookup(nip):
    """{'name', 'street', 'post_code', 'city', 'regon', 'kind'} or None when
    GUS has no firm with this NIP. Raises FirmClosed or GusError."""
    if not enabled():
        raise GusError("GUS_API_KEY not set")
    sid = _call(
        "Zaloguj",
        f"<ns:Zaloguj><ns:pKluczUzytkownika>{_key()}</ns:pKluczUzytkownika>"
        "</ns:Zaloguj>",
    )
    if not sid:
        raise GusError("GUS refused the key")
    data = _call(
        "DaneSzukajPodmioty",
        "<ns:DaneSzukajPodmioty><ns:pParametryWyszukiwania>"
        f"<dat:Nip>{nip}</dat:Nip></ns:pParametryWyszukiwania>"
        "</ns:DaneSzukajPodmioty>",
        sid=sid,
    )
    try:
        firms = ET.fromstring(data).findall("dane") if data.strip() else []
    except ET.ParseError as exc:
        raise GusError("broken GUS data") from exc
    # Several entries (e.g. a firm and its local units): the main one first.
    firms = [firm for firm in firms if not _text(firm, "ErrorCode")]
    if not firms:
        return None
    firm = firms[0]
    if _text(firm, "DataZakonczeniaDzialalnosci"):
        raise FirmClosed(_text(firm, "Nazwa"))
    # Any field may be missing in REGON - left empty, the buyer fills it in.
    # A village without streets: "Wólka 12" (the place name and the number).
    number = _text(firm, "NrNieruchomosci")
    flat = _text(firm, "NrLokalu")
    street = _text(firm, "Ulica") or (_text(firm, "Miejscowosc") if number else "")
    if street and number:
        street = f"{street} {number}" + (f"/{flat}" if flat else "")
    return {
        "name": _text(firm, "Nazwa"),
        "street": street,
        "post_code": _text(firm, "KodPocztowy"),
        "city": _text(firm, "MiejscowoscPoczty") or _text(firm, "Miejscowosc"),
        "regon": _text(firm, "Regon"),
        # P: a legal person (company), F: a natural person (sole trader).
        "kind": _text(firm, "Typ"),
    }
