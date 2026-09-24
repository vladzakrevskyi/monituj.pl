from django.contrib import admin

from apps.notifications.models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["recipient_email", "template", "status", "sent_at"]
    list_filter = ["template", "status"]
    search_fields = ["recipient_email"]
