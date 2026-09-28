import json
from types import SimpleNamespace

import pytest
import requests
from django.urls import reverse

from apps.billing import invoicing, registry
from apps.billing.models import BillingProfile
from apps.billing.services import account_for
from tests.conftest import page_text
from tests.test_billing import fake_stripe  # noqa: F401
from tests.test_invoicing import stripe_invoice

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
FIRM = {
    "kind": "company",
    "company_name": "Biuro Rachunkowe Sp. z o.o.",
    "tax_id": "PL 521-301-72-28",
    "street": "ul. Prosta 1",
    "post_code": "00-001",
    "city": "Warszawa",
    "country": "PL",
}
PERSON = {
    "kind": "person",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "street": "ul. Prosta 1",
    "post_code": "00-001",
    "city": "Warszawa",
    "country": "PL",
}


class FakeRegistry:
    """wl-api.mf.gov.pl: 'found', 'unknown' (not listed), 'invalid' or 'down'."""

    def __init__(self):
        self.answer = "found"
        self.calls = 0

    def __call__(self, method, url, params=None, timeout=None, **kwargs):
        self.calls += 1
        if self.answer == "down":
            raise requests.ConnectionError("down")
        if self.answer == "invalid":
            return _json(400, {"code": "WL-115", "message": "Nieprawidłowy NIP."})
        subject = None
        if self.answer == "found":
            subject = {
                "name": "BIURO RACHUNKOWE SPÓŁKA Z O.O.",
                "statusVat": "Czynny",
                "workingAddress": "ŚWIĘTOKRZYSKA 12, 00-916 WARSZAWA",
            }
        return _json(200, {"result": {"subject": subject}})


def _json(status, data):
    return SimpleNamespace(status_code=status, json=lambda: data, text=json.dumps(data))


@pytest.fixture
def mf(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(requests, "request", fake)
    return fake


def _save(client, data):
    return client.post(reverse("billing:profile"), data, **AJAX)


# --- Saving and checking -------------------------------------------------------


@pytest.mark.django_db
def test_person_details_are_saved(client, user):
    client.force_login(user)

    response = _save(client, PERSON)

    assert response.status_code == 200
    profile = BillingProfile.objects.get(user=user)
    assert (profile.display_name, profile.tax_id) == ("Jan Kowalski", "")


@pytest.mark.django_db
def test_firm_nip_is_checked_in_the_register(client, user, mf):
    client.force_login(user)

    _save(client, FIRM)

    profile = BillingProfile.objects.get(user=user)
    assert profile.tax_id == "5213017228"
    assert profile.registry_status == "Czynny"
    assert profile.registry_name == "BIURO RACHUNKOWE SPÓŁKA Z O.O."


@pytest.mark.django_db
def test_nip_with_a_wrong_checksum_is_refused_without_asking(client, user, mf):
    client.force_login(user)

    response = _save(client, {**FIRM, "tax_id": "4434434434"})

    assert response.status_code == 400
    assert "tax_id" in response.json()["error"]["fields"]
    assert mf.calls == 0
    assert not BillingProfile.objects.exists()


@pytest.mark.django_db
def test_nip_unknown_to_the_ministry_is_refused(client, user, mf):
    mf.answer = "invalid"
    client.force_login(user)

    response = _save(client, FIRM)

    assert response.status_code == 400
    assert (
        "Ministerstwo Finansów nie zna"
        in response.json()["error"]["fields"]["tax_id"][0]
    )


@pytest.mark.django_db
@pytest.mark.parametrize("answer", ["unknown", "down"])
def test_firm_outside_the_register_or_register_down_is_accepted(
    client, user, mf, answer
):
    mf.answer = answer
    client.force_login(user)

    response = _save(client, FIRM)

    assert response.status_code == 200
    assert BillingProfile.objects.get(user=user).registry_status == ""


@pytest.mark.django_db
def test_required_fields_and_polish_post_code(client, user):
    client.force_login(user)

    response = _save(
        client, {**PERSON, "last_name": "", "post_code": "00001", "city": ""}
    )

    fields = response.json()["error"]["fields"]
    assert set(fields) >= {"last_name", "post_code", "city"}


@pytest.mark.django_db
def test_invoices_are_for_poland_only(client, user):
    client.force_login(user)

    _save(client, {**PERSON, "country": "DE"})
    html = page_text(client.get(reverse("billing:plan")))

    assert BillingProfile.objects.get(user=user).country == "PL"
    assert 'name="country"' not in html


@pytest.mark.django_db
def test_nip_errors_sit_under_the_whole_nip_row(client, user):
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert '<span class="billing-profile__nip" data-error-for="tax_id">' in html


@pytest.mark.django_db
def test_register_lookup_fills_the_form(client, user, mf):
    client.force_login(user)

    response = client.post(reverse("billing:registry"), {"nip": "521-301-72-28"})

    assert response.json()["data"] == {
        "locked": ["company_name", "street", "post_code", "city"],
        "company_name": "BIURO RACHUNKOWE SPÓŁKA Z O.O.",
        "street": "Świętokrzyska 12",
        "post_code": "00-916",
        "city": "Warszawa",
        "status": "Czynny",
        "source": "MF",
    }


@pytest.mark.django_db
def test_register_lookups_are_limited(client, user, mf):
    client.force_login(user)

    codes = [
        client.post(reverse("billing:registry"), {"nip": "5213017228"}).status_code
        for _ in range(21)
    ]

    assert codes[-1] == 429
    assert mf.calls == 20


def test_register_address_parsing():
    assert registry.ADDRESS.match("SZLAK 49, 31-153 KRAKÓW")["city"] == "KRAKÓW"
    assert registry._pretty("AL. JANA PAWŁA II 12/4") == "Al. Jana Pawła II 12/4"


# --- Payments wait for the details ---------------------------------------------


@pytest.mark.django_db
def test_no_payment_without_invoice_details(client, user, fake_stripe):  # noqa: F811
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"),
        {"plan": "start", "interval": "month", "early_start": "on"},
        follow=True,
    )

    assert "Najpierw uzupełnij dane do faktury" in page_text(response)
    fake_stripe.v1.checkout.sessions.create.assert_not_called()


@pytest.mark.django_db
def test_plan_page_asks_for_details_first(client, user):
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert 'id="dane"' in html
    assert "Uzupełnij dane do faktury powyżej" in html
    assert 'name="early_start"' not in html


@pytest.mark.django_db
def test_saved_details_show_as_a_summary(client, user, mf):
    client.force_login(user)
    _save(client, FIRM)

    html = page_text(client.get(reverse("billing:plan")))

    # The register's official details, not what was typed.
    assert "BIURO RACHUNKOWE SPÓŁKA Z O.O." in html
    assert "NIP 5213017228" in html
    assert "Dane z rejestru MF · VAT: czynny" in html


@pytest.mark.django_db
def test_invoice_is_made_out_to_the_saved_details(client, user, mf):
    client.force_login(user)
    _save(client, FIRM)
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()

    # Whatever the buyer typed at Stripe, the checked details win.
    invoice = invoicing.queue_from_stripe(
        stripe_invoice(tax_ids=[{"type": "eu_vat", "value": "PL4434434434"}])
    )

    assert invoice.client["client_company_name"] == "BIURO RACHUNKOWE SPÓŁKA Z O.O."
    assert invoice.client["client_tax_code"] == "5213017228"


# --- GUS (REGON) ------------------------------------------------------------------


def _gus_answer(dane):
    inner = f"<root><dane>{dane}</dane></root>"
    escaped = inner.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    envelope = (
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>'
        '<DaneSzukajPodmiotyResponse xmlns="http://CIS/BIR/PUBL/2014/07">'
        f"<DaneSzukajPodmiotyResult>{escaped}</DaneSzukajPodmiotyResult>"
        "</DaneSzukajPodmiotyResponse></s:Body></s:Envelope>"
    )
    return (
        f"--uuid:1\r\nContent-Type: application/xop+xml\r\n\r\n{envelope}\r\n--uuid:1--"
    )


LOGIN = (
    '--uuid:1\r\n\r\n<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
    '<s:Body><ZalogujResponse xmlns="http://CIS/BIR/PUBL/2014/07">'
    "<ZalogujResult>sid123</ZalogujResult></ZalogujResponse></s:Body></s:Envelope>"
)
SOLE_TRADER = (
    "<Regon>123456785</Regon><Nip>5213017228</Nip>"
    "<Nazwa>Jan Kowalski Usługi Księgowe</Nazwa><Miejscowosc>Kraków</Miejscowosc>"
    "<KodPocztowy>30-549</KodPocztowy><Ulica>ul. Krucza</Ulica>"
    "<NrNieruchomosci>4</NrNieruchomosci><NrLokalu>2</NrLokalu><Typ>F</Typ>"
    "<DataZakonczeniaDzialalnosci /><MiejscowoscPoczty>Kraków</MiejscowoscPoczty>"
)


@pytest.fixture
def gus(settings, monkeypatch, mf):
    """GUS in test mode answering with `gus.dane`; MF from the `mf` fake."""
    settings.GUS_MODE = "test"
    fake = SimpleNamespace(dane=SOLE_TRADER, calls=[])

    def request(method, url, **kwargs):
        if "stat.gov.pl" not in url:
            return mf(method, url, **kwargs)
        body = kwargs["data"].decode()
        fake.calls.append((body, kwargs["headers"]))
        text = LOGIN if "Zaloguj" in body else _gus_answer(fake.dane)
        return SimpleNamespace(
            content=text.encode(), status_code=200, raise_for_status=lambda: None
        )

    monkeypatch.setattr(requests, "request", request)
    return fake


@pytest.mark.django_db
def test_gus_finds_a_firm_outside_the_vat_register(client, user, gus, mf):
    mf.answer = "unknown"  # not a VAT payer
    client.force_login(user)

    # Only the NIP is sent - nothing else.
    response = _save(
        client, {"kind": "company", "tax_id": "5213017228", "country": "PL"}
    )

    assert response.status_code == 200
    profile = BillingProfile.objects.get(user=user)
    assert profile.company_name == "Jan Kowalski Usługi Księgowe"
    assert profile.address_line == "ul. Krucza 4/2, 30-549 Kraków"
    assert (profile.registry_source, profile.registry_status) == ("GUS", "")
    assert "abcde12345abcde12345" in gus.calls[0][0]
    assert gus.calls[1][1]["sid"] == "sid123"


@pytest.mark.django_db
def test_typed_details_cannot_override_the_register(client, user, gus):
    client.force_login(user)

    _save(
        client,
        {
            "kind": "company",
            "tax_id": "5213017228",
            "country": "PL",
            "company_name": "Inna Firma",
            "street": "Fałszywa 1",
            "post_code": "00-001",
            "city": "Warszawa",
        },
    )

    profile = BillingProfile.objects.get(user=user)
    assert profile.company_name == "Jan Kowalski Usługi Księgowe"
    assert profile.city == "Kraków"
    # MF knew the NIP too: its VAT status is shown next to GUS data.
    assert profile.registry_status == "Czynny"


@pytest.mark.django_db
def test_closed_firm_is_refused(client, user, gus):
    gus.dane = SOLE_TRADER.replace(
        "<DataZakonczeniaDzialalnosci />",
        "<DataZakonczeniaDzialalnosci>2024-05-31</DataZakonczeniaDzialalnosci>",
    )
    client.force_login(user)

    response = _save(
        client, {"kind": "company", "tax_id": "5213017228", "country": "PL"}
    )

    assert "zakończyła działalność" in response.json()["error"]["fields"]["tax_id"][0]


@pytest.mark.django_db
def test_firm_no_register_knows_must_be_typed_in(client, user, gus, mf):
    gus.dane = "<ErrorCode>4</ErrorCode><ErrorMessagePl>Nie znaleziono</ErrorMessagePl>"
    mf.answer = "unknown"
    client.force_login(user)

    missing = _save(
        client, {"kind": "company", "tax_id": "5213017228", "country": "PL"}
    )
    typed = _save(client, FIRM)

    assert set(missing.json()["error"]["fields"]) >= {"company_name", "street"}
    assert typed.status_code == 200
    profile = BillingProfile.objects.get(user=user)
    assert (profile.company_name, profile.registry_source) == (
        "Biuro Rachunkowe Sp. z o.o.",
        "",
    )


@pytest.mark.django_db
def test_register_lookup_prefers_gus(client, user, gus):
    client.force_login(user)

    data = client.post(reverse("billing:registry"), {"nip": "5213017228"}).json()

    assert data["data"]["company_name"] == "Jan Kowalski Usługi Księgowe"
    assert data["data"]["source"] == "GUS"
    assert data["data"]["status"] == "Czynny"


PARTIAL = (
    "<Regon>123456785</Regon><Nip>5213017228</Nip>"
    "<Nazwa>Jan Kowalski Usługi</Nazwa><Miejscowosc>Kraków</Miejscowosc>"
    "<KodPocztowy /><Ulica /><NrNieruchomosci /><NrLokalu /><Typ>F</Typ>"
    "<DataZakonczeniaDzialalnosci /><MiejscowoscPoczty>Kraków</MiejscowoscPoczty>"
)


@pytest.mark.django_db
def test_register_details_are_locked_and_missing_ones_are_typed(client, user, gus, mf):
    # GUS knows the name and the city only; the VAT register doesn't know
    # the firm at all.
    gus.dane = PARTIAL
    mf.answer = "unknown"
    client.force_login(user)

    lookup = client.post(reverse("billing:registry"), {"nip": "5213017228"}).json()
    missing = _save(client, {"kind": "company", "tax_id": "5213017228"})
    saved = _save(
        client,
        {
            "kind": "company",
            "tax_id": "5213017228",
            "company_name": "Zmieniona Nazwa",  # locked: ignored
            "city": "Warszawa",  # locked: ignored
            "street": "ul. Długa 5",
            "post_code": "31-147",
        },
    )

    assert lookup["data"]["locked"] == ["company_name", "city"]
    assert lookup["data"]["street"] == ""
    assert set(missing.json()["error"]["fields"]) == {"street", "post_code"}
    assert saved.status_code == 200
    profile = BillingProfile.objects.get(user=user)
    assert profile.company_name == "Jan Kowalski Usługi"
    assert profile.address_line == "ul. Długa 5, 31-147 Kraków"
    assert profile.registry_fields == ["company_name", "city"]


@pytest.mark.django_db
def test_editing_keeps_register_details_locked_on_screen(client, user, gus, mf):
    gus.dane = PARTIAL
    mf.answer = "unknown"
    client.force_login(user)
    _save(
        client,
        {
            "kind": "company",
            "tax_id": "5213017228",
            "street": "ul. Długa 5",
            "post_code": "31-147",
        },
    )

    html = page_text(client.get(reverse("billing:plan")))

    assert 'name="company_name" value="Jan Kowalski Usługi"' in html
    company = html.split('name="company_name"')[1].split(">")[0]
    street = html.split('name="street"')[1].split(">")[0]
    assert "readonly" in company
    assert "readonly" not in street


def test_village_without_streets_and_missing_address(settings, monkeypatch):
    from apps.billing import gus as gus_module

    settings.GUS_MODE = "test"

    def answer(dane):
        def request(method, url, **kwargs):
            body = kwargs["data"].decode()
            text = LOGIN if "Zaloguj" in body else _gus_answer(dane)
            return SimpleNamespace(
                content=text.encode(), status_code=200, raise_for_status=lambda: None
            )

        return request

    village = PARTIAL.replace(
        "<NrNieruchomosci />", "<NrNieruchomosci>12</NrNieruchomosci>"
    ).replace("<Miejscowosc>Kraków</Miejscowosc>", "<Miejscowosc>Wólka</Miejscowosc>")
    monkeypatch.setattr(requests, "request", answer(village))
    assert gus_module.lookup("5213017228")["street"] == "Wólka 12"

    monkeypatch.setattr(requests, "request", answer(PARTIAL))
    assert gus_module.lookup("5213017228")["street"] == ""
