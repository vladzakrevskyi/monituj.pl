import pytest
from django.test import Client as BrowserClient
from django.urls import reverse

from apps.documents.models import Document
from tests.conftest import make_pdf_upload


@pytest.mark.django_db
def test_first_visit_can_upload_with_csrf_checks_on(request_record, request_item):
    # A real browser: CSRF enforced, no cookies from any earlier visit.
    browser = BrowserClient(enforce_csrf_checks=True)

    page = browser.get(
        reverse("public:request-detail", args=[request_record.public_token])
    )
    token = page.cookies["csrftoken"].value
    upload = browser.post(
        f"/api/public/{request_record.public_token}/items/{request_item.pk}/upload/",
        {"file": make_pdf_upload()},
        HTTP_X_CSRFTOKEN=token,
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert upload.status_code == 201, upload.content
    assert Document.objects.filter(request_item=request_item).exists()
