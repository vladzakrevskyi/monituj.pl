from django.contrib import admin

from apps.reminders.models import Reminder


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ["request", "kind", "sequence_number", "sent_at", "triggered_by"]
    list_filter = ["kind"]
