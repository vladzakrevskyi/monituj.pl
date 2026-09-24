from django.urls import path

from apps.requests import public_views

app_name = "public"

urlpatterns = [
    path("d/<str:token>/", public_views.public_request_detail, name="request-detail"),
    path(
        "wyslij-prosbe/", public_views.guest_request_create, name="guest-request-create"
    ),
    path(
        "wyslij-prosbe/utworzono/<str:token>/",
        public_views.guest_request_created,
        name="guest-request-created",
    ),
]
