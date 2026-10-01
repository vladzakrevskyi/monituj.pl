from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("powiadomienia/", views.notification_list, name="list"),
    path("opinia/<str:token>/", views.review, name="review"),
    path("opinia/<str:token>/rezygnacja/", views.review_stop, name="review-stop"),
]
