import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client
from apps.requests.models import Request
from apps.requests.services import RequestService

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def clients(user):
    return [
        Client.objects.create(owner=user, name=f"Klient {n}", email=f"k{n}@example.com")
        for n in range(1, 4)
    ]


def _send(client, clients, **extra):
    data = {
        "recipients": "many",
        "clients": [c.pk for c in clients],
        "name": "Dokumenty za wrzesień",
        "items": ["Faktury", "Wyciąg"],
        "retention_choice": "90",
        **extra,
    }
    return client.post(reverse("requests:create"), data, **AJAX)


@pytest.mark.django_db
def test_one_request_per_client_invitations_from_the_queue(client, user, clients):
    client.force_login(user)

    response = _send(client, clients)

    assert response.json()["data"]["redirect_url"] == reverse("requests:list")
    requests = Request.objects.order_by("client__name")
    assert [r.client for r in requests] == clients
    assert all(r.items.count() == 2 for r in requests)
    # Nothing sent inside the page request...
    assert mail.outbox == []
    assert all(r.invitation_queued for r in requests)
    # ...the queue sends each invitation once.
    assert RequestService.send_queued_invitations() == 3
    assert RequestService.send_queued_invitations() == 0
    assert sorted(m.to[0] for m in mail.outbox) == [c.email for c in clients]
    assert all(
        r.public_token in m.body
        for r, m in zip(
            requests, sorted(mail.outbox, key=lambda m: m.to[0]), strict=True
        )
    )


@pytest.mark.django_db
def test_all_or_nothing_when_the_plan_has_too_few_places(client, user, clients):
    from django.utils import timezone

    from apps.billing.services import account_for

    # Free plan: 3 requests in progress, one already used.
    account = account_for(user)
    account.trial_ends_at = timezone.now()
    account.save()
    Request.objects.create(client=clients[0], created_by=user, name="Stara")
    Request.objects.get().items.create(name="Faktura")
    client.force_login(user)

    response = _send(client, clients)

    assert response.status_code == 400
    assert "wolnych miejsc zostało 2, a wybrano 3" in str(response.json())
    assert Request.objects.count() == 1


@pytest.mark.django_db
def test_no_password_for_many_clients(client, user, clients):
    client.force_login(user)

    response = _send(client, clients, password="Tajne-haslo-1")

    assert "password" in response.json()["error"]["fields"]
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_someone_elses_client_cannot_be_ticked(client, user, clients):
    other = User.objects.create_user(email="inny@example.com", password="x-pass-1!")
    foreign = Client.objects.create(owner=other, name="Obcy", email="o@example.com")
    client.force_login(user)

    response = _send(client, [clients[0], foreign])

    assert "clients" in response.json()["error"]["fields"]
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_closed_before_sending_is_not_sent(client, user, clients):
    client.force_login(user)
    _send(client, clients[:2])
    Request.objects.update(closed_at="2026-09-29T10:00Z")

    assert RequestService.send_queued_invitations() == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_one_field_for_one_client_or_many(client, user, clients):
    client.force_login(user)

    page = client.get(reverse("requests:create")).content.decode()

    assert "data-recipient-picker" in page
    # The clients to pick from, for the search as you type.
    assert '"email": "k1@example.com"' in page


def _typed(*rows):
    return {
        "new_clients_name": [name for name, _ in rows],
        "new_clients_email": [email for _, email in rows],
    }


@pytest.mark.django_db
def test_new_clients_typed_in_are_saved_and_asked(client, user):
    client.force_login(user)

    response = _send(
        client,
        [],
        **_typed(("Jan Kowalski", "jan@firma.pl"), ("", "ewa@biuro.pl"), ("", "")),
    )

    assert response.status_code == 200
    assert sorted(Client.objects.values_list("name", "email")) == [
        ("Jan Kowalski", "jan@firma.pl"),
        ("ewa", "ewa@biuro.pl"),
    ]
    assert Request.objects.count() == 2


@pytest.mark.django_db
def test_ticked_and_typed_together_each_client_once(client, user, clients):
    client.force_login(user)

    _send(
        client,
        clients[:2],
        # An address already on the list is that client; a repeat counts once.
        **_typed(
            ("", clients[0].email.upper()),
            ("Nowy", "nowy@firma.pl"),
            ("", "NOWY@firma.pl"),
        ),
    )

    assert Client.objects.count() == 4
    assert sorted(Request.objects.values_list("client__email", flat=True)) == [
        "k1@example.com",
        "k2@example.com",
        "nowy@firma.pl",
    ]


@pytest.mark.django_db
def test_a_bad_row_stops_everything(client, user):
    client.force_login(user)

    response = _send(
        client, [], **_typed(("Jan", "jan@firma.pl"), ("Ewa", ""), ("", "nie-email"))
    )

    errors = response.json()["error"]["fields"]["new_clients"]
    assert "Podaj adres email klienta „Ewa”." in errors
    assert "Nieprawidłowy adres email: nie-email" in errors
    assert not Client.objects.exists()
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_nothing_chosen(client, user):
    client.force_login(user)

    response = _send(client, [])

    assert "clients" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_new_clients_are_not_kept_when_the_plan_is_full(client, user):
    from django.utils import timezone

    from apps.billing.services import account_for

    account = account_for(user)
    account.trial_ends_at = timezone.now()
    account.save()
    client.force_login(user)

    response = _send(client, [], **_typed(*[("", f"n{n}@firma.pl") for n in range(4)]))

    assert response.status_code == 400
    assert not Client.objects.exists()
    assert not Request.objects.exists()
