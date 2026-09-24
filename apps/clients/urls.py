from django.urls import path

from apps.clients import views

app_name = "clients"

urlpatterns = [
    path("klienci/", views.client_list, name="list"),
    path("klienci/nowy/", views.client_create, name="create"),
    path("klienci/<int:client_id>/edytuj/", views.client_edit, name="edit"),
    path(
        "klienci/<int:client_id>/dokumenty/",
        views.client_documents,
        name="documents",
    ),
]
