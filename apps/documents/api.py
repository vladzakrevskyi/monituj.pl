import json
import mimetypes

from django.http import FileResponse
from django.views.decorators.http import require_http_methods

from apps.common import throttle
from apps.common.decorators import api_login_required
from apps.common.exceptions import ValidationAppError
from apps.common.formatting import format_datetime
from apps.common.responses import error_response, success_response
from apps.documents.services import (
    UPLOADS_PER_IP_HOUR,
    DocumentAccessService,
    DocumentReviewService,
    GuestDeleteService,
    UploadDocumentService,
)
from apps.documents.storage import private_storage
from apps.requests.models import RequestItem
from apps.requests.services import PublicAccessService, RequestService


@require_http_methods(["POST"])
def public_upload_item(request, token, item_id):
    request_obj = PublicAccessService.get_by_token(token)
    if not PublicAccessService.has_access(request_obj, request):
        return error_response(
            "LOCKED", "Brak dostępu. Otwórz najpierw link do dokumentów.", status=403
        )

    item = RequestItem.objects.filter(pk=item_id, request=request_obj).first()
    if item is None:
        return error_response("NOT_FOUND", "Nie znaleziono dokumentu.", status=404)

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        raise ValidationAppError("Wybierz plik do przesłania.", code="FILE_REQUIRED")
    throttle.consume(
        throttle.ip_key("upload", request),
        UPLOADS_PER_IP_HOUR,
        throttle.HOUR,
        "Przesłano bardzo dużo plików w krótkim czasie. Spróbuj ponownie za godzinę.",
        code="UPLOAD_LIMIT_REACHED",
    )

    document = UploadDocumentService.upload_for_item(
        item, uploaded_file, django_request=request
    )
    item.refresh_from_db()

    return success_response(
        {
            "item": {
                "id": item.pk,
                "status": {"code": item.status, "label": item.get_status_display()},
            },
            "document": {
                "id": document.pk,
                "original_filename": document.original_filename,
                "uploaded_at": document.uploaded_at.isoformat(),
                "uploaded_at_display": format_datetime(document.uploaded_at),
            },
        },
        status=201,
    )


@require_http_methods(["DELETE"])
def public_delete_document(request, document_id):
    item = GuestDeleteService.delete_own_upload(document_id, request)
    return success_response(
        {
            "item": {
                "id": item.pk,
                "status": {"code": item.status, "label": item.get_status_display()},
            }
        }
    )


@require_http_methods(["GET"])
def download_document(request, document_id):
    document = DocumentAccessService.get_for_download(document_id, request)
    file_handle = private_storage.open(document.storage_key, "rb")
    content_type = (
        mimetypes.guess_type(document.original_filename)[0]
        or "application/octet-stream"
    )
    response = FileResponse(
        file_handle, as_attachment=True, filename=document.original_filename
    )
    response["Content-Type"] = content_type
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_login_required
@require_http_methods(["POST"])
def accept_item(request, request_id, item_id):
    request_obj = RequestService.get_owned_request(request.user, request_id)
    item = RequestItem.objects.filter(pk=item_id, request=request_obj).first()
    if item is None:
        return error_response("NOT_FOUND", "Nie znaleziono dokumentu.", status=404)

    DocumentReviewService.accept(item, request=request)
    return success_response(
        {
            "item": {
                "id": item.pk,
                "status": {"code": item.status, "label": item.get_status_display()},
            }
        }
    )


@api_login_required
@require_http_methods(["POST"])
def reject_item(request, request_id, item_id):
    request_obj = RequestService.get_owned_request(request.user, request_id)
    item = RequestItem.objects.filter(pk=item_id, request=request_obj).first()
    if item is None:
        return error_response("NOT_FOUND", "Nie znaleziono dokumentu.", status=404)

    try:
        data = json.loads(request.body) if request.body else {}
    except ValueError as exc:
        raise ValidationAppError(
            "Nieprawidłowe dane JSON.", code="INVALID_JSON"
        ) from exc

    DocumentReviewService.reject(item, data.get("reason", ""), request=request)
    return success_response(
        {
            "item": {
                "id": item.pk,
                "status": {"code": item.status, "label": item.get_status_display()},
            }
        }
    )
