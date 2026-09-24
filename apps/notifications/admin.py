from django.contrib import admin

from apps.notifications.models import EmailLog, Notification


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["recipient_email", "template", "status", "sent_at"]
    list_filter = ["template", "status"]
    search_fields = ["recipient_email"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "created_at", "read_at", "emailed_at"]
    list_filter = ["kind"]
    raw_id_fields = ["user", "document"]
