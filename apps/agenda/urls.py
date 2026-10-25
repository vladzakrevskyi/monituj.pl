from django.urls import path

from apps.agenda import views

app_name = "agenda"

urlpatterns = [
    path("kalendarz/", views.calendar_page, name="calendar"),
    path("kalendarz/przypomnienia/", views.reminder_add, name="reminder-add"),
    path(
        "kalendarz/przypomnienia/<int:reminder_id>/zrobione/",
        views.reminder_done,
        name="reminder-done",
    ),
    path(
        "kalendarz/przypomnienia/<int:reminder_id>/usun/",
        views.reminder_delete,
        name="reminder-delete",
    ),
    path("kalendarz/poranny-email/", views.daily_email, name="daily-email"),
    path("kalendarz/link/", views.feed_link, name="feed-link"),
    path("kalendarz/ics/<str:token>.ics", views.feed, name="feed"),
]
