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
    created = RequestService.create(
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
    page = response.content.decode()
    assert "Aktywne prośby" in page
    # The activity names the request and links to it.
    assert "Widoczne zadanie" in page
    assert reverse("requests:detail", args=[created.pk]) in page


def _sent(user, client_record, name, deadline=None, days_ago=0):
    from datetime import timedelta

    from django.utils import timezone

    from apps.requests.models import Request

    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name=name,
        description="",
        deadline=deadline,
        item_names=["A"],
    )
    Request.objects.filter(pk=request_obj.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return request_obj


@pytest.mark.django_db
def test_unopened_lists_links_nobody_opened_for_days(user, client_record):
    from django.contrib.contenttypes.models import ContentType

    from apps.audit.models import AuditEvent, AuditLog
    from apps.requests.models import Request

    old = _sent(user, client_record, "Stara", days_ago=5)
    opened = _sent(user, client_record, "Otwarta", days_ago=5)
    _sent(user, client_record, "Świeża", days_ago=1)
    AuditLog.objects.create(
        event=AuditEvent.PUBLIC_LINK_ACCESSED,
        content_type=ContentType.objects.get_for_model(Request),
        object_id=opened.pk,
    )

    assert [r.pk for r in DashboardService.unopened(user)] == [old.pk]
    kinds = [entry["kind"] for entry in DashboardService.to_do(user)]
    assert kinds == ["unopened"]


@pytest.mark.django_db
def test_upcoming_shows_deadlines_of_the_next_week(user, client_record):
    from datetime import timedelta

    from django.utils import timezone

    soon = _sent(user, client_record, "Za 3 dni", timezone.now() + timedelta(days=3))
    _sent(user, client_record, "Za miesiąc", timezone.now() + timedelta(days=30))
    _sent(user, client_record, "Po terminie", timezone.now() - timedelta(days=1))

    assert [r.pk for r in DashboardService.upcoming(user)] == [soon.pk]


@pytest.mark.django_db
def test_month_counts_clients_with_everything(user, client_record):
    _sent(user, client_record, "Ten miesiąc")

    month = DashboardService.for_owner(user)["month"]

    assert month["total"] == 1
    assert month["complete"] == 0
    assert month["waiting"] == 1
    assert month["remindable"] == 1
