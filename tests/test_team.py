"""Teams and workspaces: everyone has their own account and may work in
any number of firms' teams, switching between them; nothing crosses from
one workspace to another, seats come with the plan, and the plan, the team
and the firm's details stay the owner's."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts import team
from apps.accounts.models import TeamMembership, User
from apps.audit.models import AuditEvent, AuditLog
from apps.billing.services import account_for
from apps.clients.models import Client
from apps.consents.models import LegalAcceptance
from apps.requests.models import Request
from tests.conftest import make_pdf_upload, page_text

PASSWORD = "Bardzo-Tajne-Haslo-1"


def _expire_trial(user):
    account = account_for(user)
    account.trial_ends_at = timezone.now() - timedelta(days=1)
    account.save()


def _invite_path(mailoutbox):
    link = re.search(r"https?://\S+/zespol/zaproszenie/[^/\s]+/", mailoutbox[-1].body)
    return "/" + link[0].split("://", 1)[1].split("/", 1)[1]


def _join(client, owner, email, mailoutbox, name="Anna Nowak"):
    client.logout()
    team.invite(owner, email)
    client.post(
        _invite_path(mailoutbox),
        {
            "name": name,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )
    return User.objects.get(email=email)


def _switch(client, owner):
    client.post(reverse("accounts:workspace"), {"owner": owner.pk})


def _person(email):
    return User.objects.create_user(
        email=email, password=PASSWORD, email_verified_at=timezone.now()
    )


@pytest.fixture
def member(client, user, mailoutbox):
    return _join(client, user, "anna@biuro.pl", mailoutbox)


# --- joining -----------------------------------------------------------------------


@pytest.mark.django_db
def test_invited_person_joins_and_lands_in_the_team(
    client, user, mailoutbox, client_record
):
    team.invite(user, "anna@biuro.pl")
    assert "zaprasza Cię do zespołu" in mailoutbox[-1].subject

    member = _join(client, user, "anna@biuro.pl", mailoutbox)

    assert TeamMembership.objects.filter(owner=user, user=member).exists()
    assert member.is_email_verified and member.check_password(PASSWORD)
    # Signed in, in the firm's workspace.
    assert client_record.name in page_text(client.get(reverse("clients:list")))
    # Everyone has an own account - all documents accepted, like at sign-up.
    documents = set(
        LegalAcceptance.objects.filter(user=member).values_list("document", flat=True)
    )
    assert documents == {"regulamin", "umowa_powierzenia", "polityka_prywatnosci"}


@pytest.mark.django_db
def test_an_unknown_link_does_not_work(client):
    assert "Link nie działa" in page_text(client.get("/zespol/zaproszenie/nieznany/"))


@pytest.mark.django_db
def test_someone_with_their_own_clients_joins_and_keeps_them_apart(
    client, user, client_record, mailoutbox
):
    piotr = _person("piotr@biuro.pl")
    Client.objects.create(owner=piotr, name="Klient Piotra", email="kp@example.com")
    team.invite(user, piotr.email)
    path = _invite_path(mailoutbox)

    assert "Zaloguj się, aby dołączyć" in page_text(client.get(path))
    client.force_login(piotr)
    client.post(path)

    team_page = page_text(client.get(reverse("clients:list")))
    assert client_record.name in team_page and "Klient Piotra" not in team_page
    _switch(client, piotr)
    own_page = page_text(client.get(reverse("clients:list")))
    assert "Klient Piotra" in own_page and client_record.name not in own_page


@pytest.mark.django_db
def test_one_person_in_two_teams(client, user, mailoutbox):
    other = _person("inna@firma.pl")
    Client.objects.create(owner=other, name="Klient innej firmy", email="o@e.com")
    Client.objects.create(owner=user, name="Klient pierwszej", email="p@e.com")
    anna = _join(client, user, "anna@biuro.pl", mailoutbox)
    team.invite(other, anna.email)
    client.force_login(anna)
    client.post(_invite_path(mailoutbox))

    assert "Klient innej firmy" in page_text(client.get(reverse("clients:list")))
    _switch(client, user)
    page = page_text(client.get(reverse("clients:list")))
    assert "Klient pierwszej" in page and "Klient innej firmy" not in page
    # The switcher lists the own account and both teams.
    panel = page_text(client.get(reverse("accounts:panel")))
    assert "Moje konto" in panel and "Biuro Testowe" in panel
    assert "inna@firma.pl" in panel


@pytest.mark.django_db
def test_cannot_join_twice_or_ones_own_team(user, member):
    with pytest.raises(Exception, match="już w tym zespole"):
        team.invite(user, member.email)
    with pytest.raises(Exception, match="Twój adres"):
        team.invite(user, user.email)


# --- working together ---------------------------------------------------------------


@pytest.mark.django_db
def test_member_works_on_the_firms_clients_and_requests(
    client, user, member, client_record, request_record, request_item
):
    from apps.documents.services import UploadDocumentService

    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    detail = client.get(reverse("requests:detail", args=[request_record.pk]))
    assert detail.status_code == 200
    download = client.get(reverse("documents_api:download", args=[document.pk]))
    assert download.status_code == 200
    accept = client.post(
        f"/api/requests/{request_record.pk}/items/{request_item.pk}/accept/"
    )
    assert accept.status_code == 200
    client.post(
        reverse("clients:create"), {"name": "Nowy", "email": "nowy@example.com"}
    )
    assert Client.objects.get(email="nowy@example.com").owner == user
    # The history says who did it.
    assert AuditLog.objects.get(event=AuditEvent.DOCUMENT_ACCEPTED).actor == member
    page = page_text(client.get(reverse("requests:detail", args=[request_record.pk])))
    assert "Dokument zaakceptowany - Anna Nowak" in page


@pytest.mark.django_db
def test_a_link_to_another_workspace_switches_to_it(
    client, user, member, request_record
):
    _switch(client, member)  # in the member's own account

    response = client.get(reverse("requests:detail", args=[request_record.pk]))

    assert response.status_code == 302
    followed = client.get(response.url)
    assert followed.status_code == 200
    assert "Przełączono na: Biuro Testowe" in page_text(followed)


@pytest.mark.django_db
def test_nothing_crosses_to_a_firm_one_isnt_in(client, member):
    stranger = _person("obca@firma.pl")
    foreign_client = Client.objects.create(
        owner=stranger, name="Cudzy klient", email="cudzy@example.com"
    )
    foreign_request = Request.objects.create(
        client=foreign_client, created_by=stranger, name="Cudza prośba"
    )

    assert "Cudzy klient" not in page_text(client.get(reverse("clients:list")))
    assert (
        client.get(reverse("requests:detail", args=[foreign_request.pk])).status_code
        == 404
    )
    assert client.get(f"/api/clients/{foreign_client.pk}/").status_code == 404
    client.post(reverse("accounts:workspace"), {"owner": stranger.pk})
    assert "Cudzy klient" not in page_text(client.get(reverse("clients:list")))


@pytest.mark.django_db
def test_plan_and_team_of_a_firm_stay_the_owners(client, user, member):
    assert client.get(reverse("billing:plan")).url == reverse("accounts:panel")
    assert client.get(reverse("accounts:team")).url == reverse("accounts:panel")
    # In the member's own account they are the owner.
    _switch(client, member)
    assert client.get(reverse("billing:plan")).status_code == 200
    assert client.get(reverse("accounts:team")).status_code == 200


# --- seats --------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_trial_plan_gives_five_seats(user):
    for number in range(4):
        team.invite(user, f"osoba{number}@biuro.pl")

    with pytest.raises(Exception, match="nie ma wolnego miejsca"):
        team.invite(user, "szosta@biuro.pl")


@pytest.mark.django_db
def test_free_plan_has_no_team(user):
    _expire_trial(user)

    with pytest.raises(Exception, match="nie ma wolnego miejsca"):
        team.invite(user, "anna@biuro.pl")


@pytest.mark.django_db
def test_over_the_seats_the_team_workspace_waits(client, user, member):
    _expire_trial(user)  # Free: the owner alone

    response = client.get(reverse("clients:list"))
    assert response.status_code == 403
    assert "Dostęp wstrzymany" in page_text(response)
    assert client.get("/api/clients/").status_code == 403
    # Their own account works as always.
    _switch(client, member)
    assert client.get(reverse("clients:list")).status_code == 200


@pytest.mark.django_db
def test_pausing_one_frees_the_seat_for_another(client, user, mailoutbox):
    from apps.billing import plans

    _join(client, user, "pierwsza@biuro.pl", mailoutbox)
    _join(client, user, "druga@biuro.pl", mailoutbox)
    account = account_for(user)
    account.trial_plan = plans.START.code
    account.save()
    first, second = team.members(user)

    assert team.has_access(first) and not team.has_access(second)
    team.set_access(user, first, False)
    assert team.has_access(second)


# --- leaving ------------------------------------------------------------------------


@pytest.mark.django_db
def test_removed_member_keeps_their_own_account(
    client, user, member, client_record, mailoutbox
):
    Client.objects.create(owner=member, name="Klient Anny", email="ka@example.com")

    team.remove(user, team.members(user).get())

    assert not TeamMembership.objects.exists()
    assert "Nie należysz już do zespołu" in mailoutbox[-1].subject
    page = page_text(client.get(reverse("clients:list")))
    assert "Klient Anny" in page and client_record.name not in page


@pytest.mark.django_db
def test_member_leaves_from_the_settings(client, user, member):
    assert "Zespoły, do których należysz" in page_text(
        client.get(reverse("accounts:settings"))
    )

    client.post(reverse("accounts:team-leave"), {"owner": user.pk})

    assert not TeamMembership.objects.exists()
    assert client.get(reverse("clients:list")).status_code == 200


@pytest.mark.django_db
def test_deleting_the_firm_keeps_the_members_accounts(user, member, mailoutbox):
    from apps.accounts.erasure import erase_account

    erase_account(user)

    assert User.objects.filter(pk=member.pk).exists()
    assert not TeamMembership.objects.exists()


@pytest.mark.django_db
def test_a_member_deleting_their_account_leaves_the_firms_history(
    client, user, member, request_record, request_item
):
    from apps.accounts.erasure import erase_account
    from apps.documents.services import UploadDocumentService

    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    client.post(f"/api/requests/{request_record.pk}/items/{request_item.pk}/accept/")

    erase_account(member)

    entry = AuditLog.objects.get(event=AuditEvent.DOCUMENT_ACCEPTED)
    assert entry.actor is None


# --- joining by signing in -----------------------------------------------------------


@pytest.mark.django_db
def test_opening_the_link_then_signing_in_joins_the_team(
    client, user, client_record, mailoutbox
):
    piotr = _person("piotr@biuro.pl")
    team.invite(user, piotr.email)
    client.get(_invite_path(mailoutbox))  # not signed in yet

    response = client.post(
        reverse("accounts:login"), {"email": piotr.email, "password": PASSWORD}
    )

    assert response.status_code == 302
    assert TeamMembership.objects.filter(owner=user, user=piotr).exists()
    # Straight into the team's workspace, saying so.
    page = page_text(client.get(reverse("clients:list")))
    assert client_record.name in page
    assert "Dołączono do zespołu Biuro Testowe" in page


@pytest.mark.django_db
def test_any_sign_in_joins_google_included(rf, user, mailoutbox):
    """Google and the second step sign in with django's login too - the
    pending invitation goes with the session, whatever page comes next."""
    from django.contrib.auth import login
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore

    piotr = _person("piotr@biuro.pl")
    team.invite(user, piotr.email)
    raw = _invite_path(mailoutbox).rstrip("/").rsplit("/", 1)[1]
    request = rf.get("/logowanie/google/powrot/")
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    team.remember(request, raw)

    login(request, piotr, backend="django.contrib.auth.backends.ModelBackend")

    assert TeamMembership.objects.filter(owner=user, user=piotr).exists()
    assert request.session[team.SESSION_KEY] == user.pk


@pytest.mark.django_db
def test_signing_in_to_another_address_does_not_join(client, user, mailoutbox):
    team.invite(user, "piotr@biuro.pl")
    client.get(_invite_path(mailoutbox))
    other = _person("ktos@inny.pl")

    client.post(reverse("accounts:login"), {"email": other.email, "password": PASSWORD})

    assert not TeamMembership.objects.exists()
    assert "To zaproszenie jest dla piotr@biuro.pl" in page_text(
        client.get(reverse("accounts:panel"))
    )


# --- what only the owner may delete ------------------------------------------------


@pytest.mark.django_db
def test_member_cannot_wipe_the_firm(
    client, user, member, client_record, request_record
):
    clients_before = Client.objects.filter(owner=user).count()

    client.post(reverse("clients:bulk-delete"), {"all": "1"})
    client.post(reverse("requests:bulk-delete"), {"all": "1"})
    client.post(
        reverse("requests:delete", args=[request_record.pk]), {"with_client": "1"}
    )
    api = client.delete(f"/api/clients/{client_record.pk}/?with_history=1")

    assert api.status_code == 403
    assert Client.objects.filter(owner=user).count() == clients_before
    assert Request.objects.filter(pk=request_record.pk).exists()
    # The list offers no bulk deleting to a member.
    page = client.get(reverse("clients:list")).content.decode()
    assert 'id="bulk-form"' not in page and "data-select-row" not in page


@pytest.mark.django_db
def test_member_still_deletes_a_single_request(client, user, member, request_record):
    client.post(reverse("requests:delete", args=[request_record.pk]))

    assert not Request.objects.filter(pk=request_record.pk).exists()
    assert Client.objects.filter(pk=request_record.client_id).exists()


@pytest.mark.django_db
def test_owner_keeps_bulk_deleting(client, user, client_record):
    client.force_login(user)

    page = client.get(reverse("clients:list")).content.decode()
    client.post(reverse("clients:bulk-delete"), {"ids": [client_record.pk]})

    assert 'id="bulk-form"' in page
    assert not Client.objects.filter(pk=client_record.pk).exists()


# --- an account never confirmed ---------------------------------------------------


@pytest.mark.django_db
def test_an_unconfirmed_account_joins_by_setting_a_password(client, user, mailoutbox):
    old = User.objects.create_user(email="nv@biuro.pl", password="stare-haslo")
    team.invite(user, old.email)
    path = _invite_path(mailoutbox)

    assert "Ustaw swoje konto" in page_text(client.get(path))
    client.post(
        path,
        {
            "name": "Nowa Osoba",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )

    old.refresh_from_db()
    assert old.is_email_verified and old.check_password(PASSWORD)
    assert TeamMembership.objects.filter(owner=user, user=old).exists()


# --- importing into the workspace it was started in --------------------------------


@pytest.mark.django_db
def test_an_import_lands_where_the_file_was_uploaded(client, user, member):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("k.csv", b"Nazwa;Email\nNowa firma;nf@example.com\n")
    preview = client.post(reverse("clients:import"), {"file": upload}).url
    _switch(client, member)  # to the own account before clicking "Importuj"

    assert "import do: <strong>Biuro Testowe</strong>" in page_text(client.get(preview))
    client.post(preview, {"naglowek": "1", "kolumna": ["name", "email"]})

    assert Client.objects.get(email="nf@example.com").owner == user
