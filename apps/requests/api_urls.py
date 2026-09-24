from django.urls import path

from apps.requests import api

app_name = "requests_api"

urlpatterns = [
    path("requests/", api.requests_collection, name="collection"),
    path("requests/<int:request_id>/", api.request_detail, name="detail"),
    path("requests/<int:request_id>/send-link/", api.send_link, name="send-link"),
]
