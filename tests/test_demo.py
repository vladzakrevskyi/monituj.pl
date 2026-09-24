from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client as TestClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.demo.models import DemoAccount
from apps.demo.services import DEMO_MAX_PER_IP, DemoService
from apps.documents.models import Document
from apps.documents.storage import private_storage, read_document_file
from apps.notifications.models import EmailLog, EmailStatus
from apps.requests.models import Request


def _start(client):
    return client.post(reverse("demo:start"))


def _demo_user():
    return DemoAccount.objects.get().user


@pytest.mark.django_db
def test_start_creates_seeded_demo_account_and_logs_in(client):
    response = _start(client)

    assert response.status_code == 302
    assert response.url == reverse("accounts:panel")
    user = _demo_user()
    assert Client.objects.filter(owner=user).count() == 5
    assert Request.objects.filter(created_by=user).count() == 4
    documents = Document.objects.filter(request_item__request__created_by=user)
    assert documents.exists()
    assert all(private_storage.exists(d.storage_key) for d in documents)
    assert client.get(reverse("accounts:panel")).status_code == 200


@pytest.mark.django_db
def test_demo_files_are_valid_pdfs(client):
    _start(client)
    document = Document.objects.first()

    content = read_document_file(document)

    assert content.startswith(b"%PDF-1.4")
    assert content.rstrip().endswith(b"%%EOF")


@pytest.mark.django_db
def test_start_requires_post(client):
    assert client.get(reverse("demo:start")).status_code == 405
    assert not DemoAccount.objects.exists()


@pytest.mark.django_db
def test_start_does_not_replace_a_logged_in_real_account(client, user):
    client.force_login(user)

    _start(client)

    assert not DemoAccount.objects.exists()
    assert client.get(reverse("accounts:panel")).context["user"] == user


@pytest.mark.django_db
def test_start_is_limited_per_ip(client):
    for _ in range(DEMO_MAX_PER_IP):
        TestClient().post(reverse("demo:start"))

    response = _start(client)

    assert response.url == reverse("pages:demo")
    assert DemoAccount.objects.count() == DEMO_MAX_PER_IP


@pytest.mark.django_db
def test_demo_account_never_sends_email(client):
    _start(client)
    mail.outbox.clear()

    response = client.post(
        reverse("requests:create"),
        {
            "new_client_email": "prawdziwy.adres@example.com",
            "name": "Prośba z demo",
            "items": ["Faktura"],
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 200
    assert mail.outbox == []
    logs = EmailLog.objects.filter(request__name="Prośba z demo")
    assert logs.exists()
    assert set(logs.values_list("status", flat=True)) == {EmailStatus.SKIPPED}


@pytest.mark.django_db
def test_demo_settings_are_read_only(client):
    _start(client)
    user = _demo_user()

    response = client.post(
        reverse("accounts:settings"),
        {"form_action": "profile", "display_name": "Zmienione"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    user.refresh_from_db()
    assert response.status_code == 403
    assert user.display_name != "Zmienione"


@pytest.mark.django_db
def test_panel_shows_demo_bar_with_client_view_link(client):
    _start(client)
    showcase = DemoService.showcase_request(_demo_user())

    content = client.get(reverse("accounts:panel")).content.decode()

    assert "demo-bar" in content
    assert f"/d/{showcase.public_token}/" in content


@pytest.mark.django_db
def test_end_deletes_everything_and_logs_out(
    client, django_capture_on_commit_callbacks
):
    _start(client)
    user = _demo_user()
    keys = list(
        Document.objects.filter(request_item__request__created_by=user).values_list(
            "storage_key", flat=True
        )
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("demo:end"))

    assert response.url == reverse("accounts:register")
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Request.objects.filter(created_by_id=user.pk).exists()
    assert not any(private_storage.exists(key) for key in keys)
    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_delete_expired_removes_only_expired_demo_accounts(client, user):
    _start(client)
    TestClient().post(reverse("demo:start"))
    expired, fresh = DemoAccount.objects.order_by("pk")
    DemoAccount.objects.filter(pk=expired.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert DemoService.delete_expired() == 1
    assert not User.objects.filter(pk=expired.user_id).exists()
    assert User.objects.filter(pk=fresh.user_id).exists()
    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_demo_entry_points_are_visible_to_visitors(client):
    landing = client.get("/").content.decode()
    demo_page = client.get(reverse("pages:demo"))

    assert demo_page.status_code == 200
    assert reverse("demo:start") in landing
    assert reverse("public:guest-request-create") in landing
    assert reverse("demo:start") in demo_page.content.decode()


@pytest.mark.django_db
def test_demo_start_button_hidden_for_logged_in_real_user(client, user):
    client.force_login(user)

    assert reverse("demo:start") not in client.get("/").content.decode()
