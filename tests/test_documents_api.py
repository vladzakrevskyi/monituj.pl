import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.requests.models import RequestItemStatus
from apps.requests.services import RequestService
from tests.conftest import make_fake_exe_upload, make_pdf_upload


def _visit_public_page(client, request_obj):
    client.get(reverse("public:request-detail", args=[request_obj.public_token]))


@pytest.mark.django_db
def test_public_upload_creates_document_and_updates_item(client, request_item):
    request_obj = request_item.request
    _visit_public_page(client, request_obj)
    url = reverse(
        "documents_api:upload", args=[request_obj.public_token, request_item.pk]
    )

    response = client.post(url, {"file": make_pdf_upload()})

    assert response.status_code == 201
    payload = response.json()
    assert payload["data"]["item"]["status"]["code"] == "dostarczony"
    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.DOSTARCZONY


@pytest.mark.django_db
def test_public_upload_rejects_disguised_executable(client, request_item):
    request_obj = request_item.request
    _visit_public_page(client, request_obj)
    url = reverse(
        "documents_api:upload", args=[request_obj.public_token, request_item.pk]
    )

    response = client.post(url, {"file": make_fake_exe_upload()})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MIME_NOT_ALLOWED"


@pytest.mark.django_db
def test_public_upload_locked_for_password_protected_request(
    client, user, client_record
):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    item = request_obj.items.first()
    url = reverse("documents_api:upload", args=[request_obj.public_token, item.pk])

    response = client.post(url, {"file": make_pdf_upload()})

    assert response.status_code == 403


@pytest.mark.django_db
def test_public_upload_returns_404_for_item_not_belonging_to_request(
    client, request_item
):
    from apps.clients.models import Client
    from apps.requests.models import RequestItem

    other_client = Client.objects.create(
        owner=request_item.request.created_by, name="Inny", email="inny@example.com"
    )
    other_request = RequestService.create(
        owner=request_item.request.created_by,
        client_id=other_client.pk,
        name="Inny request",
        description="",
        deadline=None,
        item_names=["X"],
    )
    unrelated_item = RequestItem.objects.get(request=other_request)

    _visit_public_page(client, request_item.request)
    url = reverse(
        "documents_api:upload",
        args=[request_item.request.public_token, unrelated_item.pk],
    )
    response = client.post(url, {"file": make_pdf_upload()})

    assert response.status_code == 404


@pytest.mark.django_db
def test_public_delete_removes_own_upload(client, request_item):
    request_obj = request_item.request
    _visit_public_page(client, request_obj)
    upload_url = reverse(
        "documents_api:upload", args=[request_obj.public_token, request_item.pk]
    )
    upload_response = client.post(upload_url, {"file": make_pdf_upload()})
    document_id = upload_response.json()["data"]["document"]["id"]

    delete_url = reverse("documents_api:public-delete", args=[document_id])
    response = client.delete(delete_url)

    assert response.status_code == 200
    assert not Document.objects.filter(pk=document_id).exists()


@pytest.mark.django_db
def test_public_delete_denied_for_different_session(client, request_item):
    from django.test import Client as DjangoTestClient

    request_obj = request_item.request
    _visit_public_page(client, request_obj)
    upload_url = reverse(
        "documents_api:upload", args=[request_obj.public_token, request_item.pk]
    )
    upload_response = client.post(upload_url, {"file": make_pdf_upload()})
    document_id = upload_response.json()["data"]["document"]["id"]

    other_client = DjangoTestClient()
    delete_url = reverse("documents_api:public-delete", args=[document_id])
    response = other_client.delete(delete_url)

    assert response.status_code == 403
    assert Document.objects.filter(pk=document_id).exists()


@pytest.mark.django_db
def test_download_requires_authorization(client, request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    url = reverse("documents_api:download", args=[document.pk])

    response = client.get(url)

    assert response.status_code == 403


@pytest.mark.django_db
def test_download_returns_file_for_owner(client, user, request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    client.force_login(user)

    response = client.get(reverse("documents_api:download", args=[document.pk]))

    assert response.status_code == 200
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_download_denies_other_owners_document(client, request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    other = User.objects.create_user(email="stranger@example.com", password="x")
    client.force_login(other)

    response = client.get(reverse("documents_api:download", args=[document.pk]))

    assert response.status_code == 403


@pytest.mark.django_db
def test_accept_endpoint_requires_login(client, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    url = reverse(
        "documents_api:accept-item", args=[request_item.request.pk, request_item.pk]
    )

    response = client.post(url)

    assert response.status_code == 401


@pytest.mark.django_db
def test_accept_endpoint_updates_status(client, user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    client.force_login(user)
    url = reverse(
        "documents_api:accept-item", args=[request_item.request.pk, request_item.pk]
    )

    response = client.post(url)

    assert response.status_code == 200
    assert response.json()["data"]["item"]["status"]["code"] == "zaakceptowany"


@pytest.mark.django_db
def test_reject_endpoint_requires_reason(client, user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    client.force_login(user)
    url = reverse(
        "documents_api:reject-item", args=[request_item.request.pk, request_item.pk]
    )

    import json

    response = client.post(
        url, data=json.dumps({"reason": ""}), content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REASON_REQUIRED"


@pytest.mark.django_db
def test_reject_endpoint_denies_cross_owner_item(client, request_item):
    other = User.objects.create_user(email="stranger2@example.com", password="x")
    client.force_login(other)
    url = reverse(
        "documents_api:reject-item", args=[request_item.request.pk, request_item.pk]
    )

    response = client.post(url)

    assert response.status_code == 404
