from django.contrib import admin

from apps.consents.models import CookieConsent, LegalAcceptance, LegalUpdateNotice


class ReadOnlyAdmin(admin.ModelAdmin):
    """Evidence: viewable, never edited or added by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(ReadOnlyAdmin):
    list_display = ["user", "document", "version", "method", "accepted_at"]
    list_filter = ["document", "version", "method"]
    search_fields = ["user__email"]


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
