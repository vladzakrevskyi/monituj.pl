import pytest
from django.urls import reverse

from apps.documents.services import DocumentReviewService, UploadDocumentService
from apps.reminders.services import ReminderService
from apps.requests.services import DashboardService, RequestService
from tests.conftest import make_pdf_upload


@pytest.mark.django_db
def test_dashboard_counts_for_owner_with_no_data(user):
    stats = DashboardService.for_owner(user)

    assert stats["active_requests"] == 0
    assert stats["missing_documents"] == 0
    assert stats["delivered_documents"] == 0
    assert stats["reminders_sent"] == 0
    assert list(stats["recent_activity"]) == []


@pytest.mark.django_db
def test_dashboard_counts_reflect_request_state(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A", "B"],
    )
    items = list(request_obj.items.all())
    UploadDocumentService.upload_for_item(items[0], make_pdf_upload())
    DocumentReviewService.accept(items[0])
    ReminderService.send_manual(request_obj, actor=user)

    stats = DashboardService.for_owner(user)

    assert stats["active_requests"] == 1
    assert stats["missing_documents"] == 1
    assert stats["delivered_documents"] == 1
    assert stats["reminders_sent"] == 1


@pytest.mark.django_db
def test_dashboard_excludes_other_owners_data(user, client_record):
    from apps.accounts.models import User
    from apps.clients.models import Client

    other = User.objects.create_user(email="other@example.com", password="x")
    other_client = Client.objects.create(
        owner=other, name="Cudzy klient", email="cudzy@example.com"
    )
    RequestService.create(
        owner=other,
        client_id=other_client.pk,
        name="Cudze",
        description="",
        deadline=None,
        item_names=["A"],
    )

    stats = DashboardService.for_owner(user)

    assert stats["active_requests"] == 0


@pytest.mark.django_db
def test_panel_view_renders_dashboard_stats(client, user, client_record):
    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Widoczne zadanie",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.get(reverse("accounts:panel"))

    assert response.status_code == 200
    assert "Aktywne prośby".encode() in response.content
    assert b"Widoczne zadanie" not in response.content
