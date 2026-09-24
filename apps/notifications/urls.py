from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("powiadomienia/", views.notification_list, name="list"),
]
