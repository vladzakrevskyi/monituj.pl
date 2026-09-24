from django.contrib import admin

from apps.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        "original_filename",
        "request_item",
        "status",
        "size",
        "uploaded_at",
    ]
    list_filter = ["status"]
    search_fields = ["original_filename", "storage_key"]
    readonly_fields = ["storage_key", "checksum"]
