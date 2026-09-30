"""The notice period: a new Regulamin (and umowa powierzenia) is published
dated ahead. Until that day the version in force is the earlier one - the
pages show it (the new one a click away), sign-ups and purchases happen on
it. Everyone is told (notify_legal_update, and new accounts as soon as they
are confirmed) and accepts the new version on its day."""

import io
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.models import User
from apps.common import legal
from apps.consents.models import AcceptanceMethod, LegalAcceptance, LegalVersion
from apps.consents.services import record_acceptance, to_accept
from tests.conftest import page_text

TODAY = timezone.localdate()
OLD = (TODAY - timedelta(days=100)).isoformat()
NEW = (TODAY + timedelta(days=15)).isoformat()
CHANGING = (legal.TERMS, legal.DPA)


@pytest.fixture
def notice_period(settings, db):
    """Regulamin and DPA get a new version in 15 days; the earlier wordings
    are in the archive. The other documents stay as they are."""
    settings.LEGAL_VERSIONS = {key: OLD for key in settings.LEGAL_VERSIONS}
    for key in CHANGING:
        title = legal.DOCUMENTS[key].title
        LegalVersion.objects.create(
            document=key,
            version=OLD,
            sha256=f"old-{key}",
            html=(
                f'<section class="document"><h1>{title}</h1>'
                f'<p class="meta">Obowiązuje od: {OLD}</p>'
                f"<p>Stara treść: {title}</p></section>"
            ),
        )
        settings.LEGAL_VERSIONS[key] = NEW


def _day_comes(monkeypatch):
    later = TODAY + timedelta(days=20)
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: later)


@pytest.mark.django_db
def test_the_page_shows_the_version_in_force_and_links_the_new_one(
    client, notice_period
):
    page = page_text(client.get(reverse("legal:terms")))

    assert "Stara treść: Regulamin" in page
    assert "Od " in page and "obowiązuje nowa wersja" in page
    assert "?wersja=nowa" in page

    new = page_text(client.get(reverse("legal:terms"), {"wersja": "nowa"}))
    assert "Stara treść" not in new
    assert "Ta wersja obowiązuje od" in new
    assert "obecna wersja" in new


@pytest.mark.django_db
def test_without_a_notice_period_the_page_is_as_always(client, settings):
    settings.LEGAL_VERSIONS = {key: OLD for key in settings.LEGAL_VERSIONS}

    page = page_text(client.get(reverse("legal:terms")))

    assert "Regulamin serwisu Monituj" in page
    assert "obowiązuje nowa wersja" not in page
    assert "legal-notice" not in page


@pytest.mark.django_db
def test_signing_up_accepts_the_version_in_force_and_the_new_one_on_its_day(
    notice_period, monkeypatch
):
    user = User.objects.create_user(email="nowy@example.com", password="x")

    record_acceptance(user, AcceptanceMethod.REGISTRATION)

    versions = set(
        LegalAcceptance.objects.filter(user=user, document=legal.TERMS).values_list(
            "version", flat=True
        )
    )
    assert versions == {OLD}
    assert to_accept(user) == []
    _day_comes(monkeypatch)
    assert set(to_accept(user)) == set(CHANGING)


@pytest.mark.django_db
def test_people_already_here_are_asked_only_from_the_day(notice_period, monkeypatch):
    user = User.objects.create_user(email="stary@example.com", password="x")
    for key in legal.ACCEPTED:
        wording = LegalVersion.objects.filter(document=key, version=OLD).first()
        if wording is None:
            from apps.consents.versions import current

            wording = current(key)
        LegalAcceptance.objects.create(
            user=user,
            document=key,
            version=OLD,
            wording=wording,
            method=AcceptanceMethod.REGISTRATION,
        )

    assert to_accept(user) == []
    _day_comes(monkeypatch)
    assert set(to_accept(user)) == set(CHANGING)


@pytest.mark.django_db
def test_the_consent_checkbox_says_it_covers_the_new_version(client, notice_period):
    page = page_text(client.get(reverse("accounts:register")))

    assert "w tym dniu poprosimy Cię o ich akceptację" in page
    assert "/regulamin/?wersja=nowa" in page


@pytest.mark.django_db
def test_the_contract_pdf_has_the_version_in_force(notice_period):
    _, content, _ = legal.contract_attachment()

    text = " ".join(
        " ".join(page.extract_text().split())
        for page in PdfReader(io.BytesIO(content)).pages
    )
    assert "Stara treść: Regulamin" in text
    assert "Regulamin serwisu Monituj" not in text  # the new wording


# --- telling people -------------------------------------------------------------


def _verified(email):
    return User.objects.create_user(
        email=email, password="x", email_verified_at=timezone.now()
    )


@pytest.mark.django_db
def test_announcement_goes_to_everyone_once(notice_period, mailoutbox):
    from django.core.management import call_command

    here = _verified("jest@example.com")
    record_acceptance(here, AcceptanceMethod.REGISTRATION)

    call_command("notify_legal_update", "--changes", "Nowe szablony.")
    call_command("notify_legal_update", "--changes", "Nowe szablony.")

    assert [m.to for m in mailoutbox] == [["jest@example.com"]]
    assert "Nowe szablony." in mailoutbox[0].body


@pytest.mark.django_db
def test_someone_joining_during_the_notice_hears_on_confirmation(
    notice_period, mailoutbox, django_capture_on_commit_callbacks
):
    from apps.accounts.services import RegistrationService, VerificationService
    from apps.consents import announcements

    announcements.publish("Nowe szablony.")
    mailoutbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        RegistrationService.register(
            email="nowy@example.com",
            password="Bardzo-Tajne-Haslo-1",
            accept_terms=True,
            accept_privacy_policy=True,
        )
    link = mailoutbox[-1].body.split("/weryfikacja-email/")[1].split("/")[0]
    mailoutbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        VerificationService.verify(link)

    assert [m.to for m in mailoutbox] == [["nowy@example.com"]]
    assert "Nowe szablony." in mailoutbox[0].body
    # The hourly task doesn't send it again.
    assert announcements.send() == 0


@pytest.mark.django_db
def test_nothing_is_sent_without_an_announcement(notice_period, mailoutbox):
    from apps.consents import announcements

    _verified("jest@example.com")

    assert announcements.send() == 0
    assert mailoutbox == []
