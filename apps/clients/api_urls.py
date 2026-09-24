from django.urls import path

from apps.clients import api

app_name = "clients_api"

urlpatterns = [
    path("clients/", api.clients_collection, name="collection"),
    path("clients/<int:client_id>/", api.client_detail, name="detail"),
]
