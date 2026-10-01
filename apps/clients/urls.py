from django.urls import path

from apps.clients import import_views, views

app_name = "clients"

urlpatterns = [
    path("klienci/", views.client_list, name="list"),
    path("klienci/nowy/", views.client_create, name="create"),
    path("klienci/usun/", views.client_bulk_delete, name="bulk-delete"),
    path("klienci/import/", import_views.client_import, name="import"),
    path(
        "klienci/import/wzor.csv",
        import_views.client_import_sample,
        name="import-sample",
    ),
    path(
        "klienci/import/<uuid:import_id>/",
        import_views.client_import_preview,
        name="import-preview",
    ),
    path("klienci/<int:client_id>/edytuj/", views.client_edit, name="edit"),
    path(
        "klienci/<int:client_id>/dokumenty/",
        views.client_documents,
        name="documents",
    ),
]
