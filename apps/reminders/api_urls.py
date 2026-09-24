from django.urls import path

from apps.reminders import api

app_name = "reminders_api"

urlpatterns = [
    path(
        "requests/<int:request_id>/remind/",
        api.send_manual_reminder,
        name="send-manual",
    ),
]
