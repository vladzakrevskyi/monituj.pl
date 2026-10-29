from django.contrib import admin

from apps.requests.models import (
    AbuseReport,
    AnonymousRequestThrottle,
    PasswordProtectedAccess,
    Request,
    RequestItem,
)


class RequestItemInline(admin.TabularInline):
    model = RequestItem
    extra = 0


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ["name", "client", "created_by", "deadline", "created_at"]
    search_fields = ["name", "public_token", "client__name"]
    list_filter = ["reminders_enabled"]
    readonly_fields = ["public_token"]
    inlines = [RequestItemInline]


@admin.register(RequestItem)
class RequestItemAdmin(admin.ModelAdmin):
    list_display = ["name", "request", "status"]
    list_filter = ["status"]


@admin.register(PasswordProtectedAccess)
class PasswordProtectedAccessAdmin(admin.ModelAdmin):
    list_display = ["request", "created_at"]
    readonly_fields = ["password_hash"]


@admin.register(AnonymousRequestThrottle)
class AnonymousRequestThrottleAdmin(admin.ModelAdmin):
    list_display = ["ip_hash", "throttle_date", "created_at"]
    list_filter = ["throttle_date"]
    readonly_fields = ["ip_hash", "throttle_date"]


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    """Recipients' "Zgłoś nadużycie" - each one was mailed as an alarm too."""

    list_display = ["created_at", "sender_email", "reason", "handled"]
    list_filter = ["handled", "reason"]
    search_fields = ["sender_email", "recipient_email"]
    readonly_fields = [
        "request",
        "sender_email",
        "recipient_email",
        "reason",
        "details",
        "created_at",
    ]
