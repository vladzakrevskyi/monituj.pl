import json
import uuid
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.common import legal
from apps.consents.models import (
    AcceptanceMethod,
    CookieConsent,
    LegalAcceptance,
    LegalDocument,
    LegalUpdateNotice,
)
from apps.consents.services import needs_acceptance, record_acceptance
from apps.consents.tasks import delete_old_cookie_consents
from apps.demo.models import DemoAccount
from tests.conftest import page_text
from tests.test_guest_requests import _form as guest_form

VERSION = "2026-09-01"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def published(settings):
    def publish(version=VERSION):
        settings.LEGAL_ENTITY = {**settings.LEGAL_ENTITY, "effective_date": version}

    publish()
    return publish


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="owner@example.com",
        password="s3cr3t-pass!",
        email_verified_at=timezone.now(),
    )


def _documents(user):
    return set(
        LegalAcceptance.objects.filter(user=user).values_list("document", flat=True)
    )


# --- 1. which version, when, from where ------------------------------------


@pytest.mark.django_db
def test_registration_records_every_document_with_its_version(client, published):
    client.post(
        reverse("accounts:register"),
        {
            "email": "nowy@example.com",
            "password": "Mocne-haslo-2026!",
            "password_confirm": "Mocne-haslo-2026!",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        REMOTE_ADDR="10.0.0.1",
        HTTP_X_FORWARDED_FOR="6.6.6.6, 83.12.34.56",
        HTTP_USER_AGENT="Firefox/140",
    )

    user = User.objects.get(email="nowy@example.com")
    rows = LegalAcceptance.objects.filter(user=user)
    assert _documents(user) == {
        "regulamin",
        "umowa_powierzenia",
        "polityka_prywatnosci",
    }
    for row in rows:
        assert row.version == VERSION
        assert row.method == AcceptanceMethod.REGISTRATION
        # The address our proxy saw, not the one the visitor wrote in.
        assert row.ip_address == "83.12.34.56"
        assert row.user_agent == "Firefox/140"
    assert user.terms_accepted_at is not None


@pytest.mark.django_db
def test_audit_log_trusts_only_the_proxy_address(client, published):
    from apps.audit.models import AuditLog

    client.post(
        reverse("accounts:login"),
        {"email": "x@example.com", "password": "wrong"},
        HTTP_X_FORWARDED_FOR="6.6.6.6, 83.12.34.56",
    )

    assert AuditLog.objects.get().ip_address == "83.12.34.56"


# --- 2. and 3. requests without an account --------------------------------


@pytest.mark.django_db
def test_request_form_accepts_the_data_processing_agreement_too(client, published):
    page = page_text(client.get(reverse("public:guest-request-create")))

    label = page[page.index('<label for="id_accept_terms">') :]
    assert 'href="/umowa-powierzenia/"' in label[: label.index("</label>")]


@pytest.mark.django_db
def test_new_sender_without_account_leaves_evidence(client, published):
    client.post(
        reverse("public:guest-request-create"),
        guest_form(),
        REMOTE_ADDR="83.1.2.3",
        **AJAX,
    )

    user = User.objects.get(email="biuro@example.com")
    assert _documents(user) == {
        "regulamin",
        "umowa_powierzenia",
        "polityka_prywatnosci",
    }
    row = LegalAcceptance.objects.filter(user=user).first()
    assert row.method == AcceptanceMethod.GUEST_REQUEST
    assert row.ip_address == "83.1.2.3"


@pytest.mark.django_db
def test_someone_typing_an_existing_address_accepts_nothing_for_it(
    client, published, verified_user
):
    client.post(
        reverse("public:guest-request-create"),
        guest_form(sender_email=verified_user.email),
        **AJAX,
    )

    assert not LegalAcceptance.objects.filter(user=verified_user).exists()


# --- 4. new version of the documents --------------------------------------


@pytest.mark.django_db
def test_panel_waits_for_the_new_version(client, published, verified_user):
    record_acceptance(verified_user, AcceptanceMethod.REGISTRATION)
    published("2026-09-20")
    client.force_login(verified_user)

    panel = client.get(reverse("requests:list"))
    api = client.get(reverse("requests_api:collection"))
    settings_page = client.get(reverse("accounts:settings"))
    refused = client.post(reverse("consents:accept"), {"next": "/przypomnienia/"})

    assert panel.status_code == 302
    assert panel["Location"].startswith(reverse("consents:accept"))
    assert api.status_code == 403
    assert api.json()["error"]["code"] == "LEGAL_ACCEPTANCE_REQUIRED"
    # Settings stay open: someone who disagrees can still delete the account.
    assert settings_page.status_code == 200
    assert refused.status_code == 200
    assert needs_acceptance(verified_user)

    accepted = client.post(
        reverse("consents:accept"),
        {
            "accept_terms": "on",
            "accept_privacy_policy": "on",
            "next": "/przypomnienia/",
        },
    )

    assert accepted["Location"] == "/przypomnienia/"
    assert client.get(reverse("requests:list")).status_code == 200
    assert (
        LegalAcceptance.objects.filter(
            user=verified_user, version="2026-09-20", method=AcceptanceMethod.UPDATE
        ).count()
        == 3
    )


@pytest.mark.django_db
def test_accounts_from_before_versions_accept_once(client, published, verified_user):
    client.force_login(verified_user)

    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_accept_page_ignores_foreign_next(client, published, verified_user):
    client.force_login(verified_user)

    response = client.post(
        reverse("consents:accept"),
        {
            "accept_terms": "on",
            "accept_privacy_policy": "on",
            "next": "https://evil.example.com/",
        },
    )

    assert response["Location"] == reverse("accounts:panel")


@pytest.mark.django_db
def test_future_version_is_shown_but_required_only_from_its_day(
    client, published, verified_user
):
    future = (timezone.localdate() + timedelta(days=14)).isoformat()
    published(future)
    client.force_login(verified_user)

    assert not legal.in_force()
    assert client.get(reverse("accounts:panel")).status_code == 200


@pytest.mark.django_db
def test_nothing_to_accept_without_a_published_version(client, verified_user):
    client.force_login(verified_user)

    assert client.get(reverse("accounts:panel")).status_code == 200


@pytest.mark.django_db
def test_demo_accounts_are_never_asked(client, published):
    demo = User.objects.create_user(email="demo@demo.monituj.pl")
    DemoAccount.objects.create(
        user=demo, expires_at=timezone.now() + timedelta(hours=1)
    )
    client.force_login(demo)

    assert client.get(reverse("accounts:panel")).status_code == 200


def test_effective_date_in_both_formats(settings):
    for raw in ("2026-10-01", "01.10.2026"):
        settings.LEGAL_ENTITY = {**settings.LEGAL_ENTITY, "effective_date": raw}
        assert legal.effective_date_display() == "1 października 2026"


# --- the email about a new version ----------------------------------------


@pytest.mark.django_db
def test_update_email_goes_once_to_every_real_account(published, verified_user):
    published((timezone.localdate() + timedelta(days=14)).isoformat())
    User.objects.create_user(email="unconfirmed@example.com")
    User.objects.create_user(
        email="inactive@example.com", is_active=False, email_verified_at=timezone.now()
    )
    newcomer = User.objects.create_user(
        email="newcomer@example.com", email_verified_at=timezone.now()
    )
    record_acceptance(newcomer, AcceptanceMethod.REGISTRATION)
    mail.outbox.clear()

    call_command("notify_legal_update", changes="Nowy cennik.")
    call_command("notify_legal_update", changes="Nowy cennik.")

    assert [m.to for m in mail.outbox] == [[verified_user.email]]
    assert "Nowy cennik." in mail.outbox[0].body
    assert LegalUpdateNotice.objects.count() == 1


@pytest.mark.django_db
def test_update_email_needs_a_dated_version(settings):
    with pytest.raises(CommandError):
        call_command("notify_legal_update", changes="x")


# --- 5. cookie consent register -------------------------------------------


@pytest.fixture
def banner(settings):
    settings.GTM_ID = "GTM-NWZ96857"
    settings.TRACKING_SERVICES = ["ga4", "meta_pixel"]
    from apps.common.cookies import consent

    return consent()["config"]


def _log(client, **body):
    return client.post(
        reverse("consents:cookie-consent"),
        json.dumps(body),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_banner_decision_is_logged_without_personal_data(client, banner):
    consent_id = str(uuid.uuid4())

    response = _log(
        client,
        id=consent_id,
        version=banner["version"],
        choices={"analytics": True, "marketing": False},
    )

    assert response.status_code == 204
    row = CookieConsent.objects.get()
    assert str(row.consent_id) == consent_id
    assert row.choices == {"analytics": True, "marketing": False}
    assert {f.name for f in CookieConsent._meta.fields} == {
        "id",
        "consent_id",
        "version",
        "choices",
        "created_at",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"id": "not-a-uuid"},
        {"version": "old"},
        {"choices": {"analytics": True}},
        {"choices": {"analytics": True, "marketing": False, "spy": True}},
        {"choices": {"analytics": "yes", "marketing": False}},
    ],
    ids=["id", "version", "missing", "extra", "not-bool"],
)
def test_malformed_decisions_are_refused(client, banner, body):
    data = {
        "id": str(uuid.uuid4()),
        "version": banner["version"],
        "choices": {"analytics": True, "marketing": False},
        **body,
    }

    assert _log(client, **data).status_code == 400
    assert not CookieConsent.objects.exists()


@pytest.mark.django_db
def test_consent_register_is_rate_limited(client, banner, monkeypatch):
    from apps.consents import views

    monkeypatch.setattr(views, "COOKIE_LOGS_PER_IP_HOUR", 2)
    body = {
        "version": banner["version"],
        "choices": {"analytics": 1 == 1, "marketing": False},
    }

    codes = [_log(client, id=str(uuid.uuid4()), **body).status_code for _ in range(3)]

    assert codes == [204, 204, 429]


@pytest.mark.django_db
def test_consent_register_keeps_three_years(db):
    CookieConsent.objects.create(
        version="v", choices={}, created_at=timezone.now() - timedelta(days=3 * 365 + 1)
    )
    CookieConsent.objects.create(version="v", choices={})

    assert delete_old_cookie_consents() == 1
    assert CookieConsent.objects.count() == 1


@pytest.mark.django_db
def test_consent_script_knows_where_to_log(client, banner):
    html = client.get("/").content.decode()

    assert f'data-log-url="{reverse("consents:cookie-consent")}"' in html


@pytest.mark.django_db
def test_policies_describe_the_evidence(client, banner):
    privacy = page_text(client.get(reverse("legal:privacy")))
    cookies = page_text(client.get(reverse("legal:cookies")))

    assert "którą wersję Regulaminu" in privacy
    assert "Rejestr zgód na cookies" in privacy
    assert "rejestrze zgód" in cookies


def test_every_document_is_recorded():
    from apps.consents.services import ALL_DOCUMENTS

    assert set(ALL_DOCUMENTS) == set(LegalDocument.values)
