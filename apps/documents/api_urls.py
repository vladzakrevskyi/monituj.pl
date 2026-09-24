from django.urls import path

from apps.documents import api

app_name = "documents_api"

urlpatterns = [
    path(
        "public/<str:token>/items/<int:item_id>/upload/",
        api.public_upload_item,
        name="upload",
    ),
    path(
        "public/documents/<int:document_id>/",
        api.public_delete_document,
        name="public-delete",
    ),
    path(
        "documents/<int:document_id>/download/", api.download_document, name="download"
    ),
    path(
        "requests/<int:request_id>/items/<int:item_id>/accept/",
        api.accept_item,
        name="accept-item",
    ),
    path(
        "requests/<int:request_id>/items/<int:item_id>/reject/",
        api.reject_item,
        name="reject-item",
    ),
]
