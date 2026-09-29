from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.consents.models import (
    CookieConsent,
    LegalAcceptance,
    LegalUpdateNotice,
    LegalVersion,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Evidence: viewable, never edited or added by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LegalVersion)
class LegalVersionAdmin(ReadOnlyAdmin):
    """Every wording of every document, as it was shown."""

    list_display = ["document", "version", "short_hash", "created_at", "accepted"]
    list_filter = ["document", "version"]
    fields = ["document", "version", "sha256", "created_at", "preview"]
    readonly_fields = fields

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Skrót treści (SHA-256)")
    def short_hash(self, obj):
        return obj.sha256[:12]

    @admin.display(description="Akceptacje")
    def accepted(self, obj):
        return obj.acceptances.count()

    @admin.display(description="Treść")
    def preview(self, obj):
        # Isolated in a frame: shown exactly as archived, without the admin's
        # styles leaking in (format_html escapes it into the attribute).
        return format_html(
            '<iframe srcdoc="{}" sandbox style="width:100%;height:70vh;'
            'border:1px solid #ccc;background:#fff"></iframe>',
            obj.html,
        )


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(ReadOnlyAdmin):
    list_display = ["user", "document", "version", "method", "accepted_at", "text"]
    list_filter = ["document", "version", "method"]
    search_fields = ["user__email"]

    @admin.display(description="Zaakceptowana treść")
    def text(self, obj):
        if obj.wording_id is None:
            return "–"
        url = reverse("admin:consents_legalversion_change", args=[obj.wording_id])
        return format_html('<a href="{}">{}</a>', url, obj.wording.sha256[:12])


@admin.register(LegalUpdateNotice)
class LegalUpdateNoticeAdmin(ReadOnlyAdmin):
    list_display = ["user", "version", "sent_at"]
    list_filter = ["version"]
    search_fields = ["user__email"]


@admin.register(CookieConsent)
class CookieConsentAdmin(ReadOnlyAdmin):
    list_display = ["consent_id", "version", "choices", "created_at"]
    list_filter = ["version"]
    search_fields = ["consent_id"]
