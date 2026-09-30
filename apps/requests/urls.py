from django.urls import path

from apps.requests import template_views, views

app_name = "requests"

urlpatterns = [
    path("przypomnienia/", views.request_list, name="list"),
    path("otrzymane/", views.received_list, name="received"),
    path("przypomnienia/nowe/", views.request_create, name="create"),
    path("przypomnienia/usun/", views.request_bulk_delete, name="bulk-delete"),
    path("przypomnienia/szablony/", template_views.template_list, name="templates"),
    path(
        "przypomnienia/szablony/nowy/",
        template_views.template_create,
        name="template-create",
    ),
    path(
        "przypomnienia/szablony/<int:template_id>/",
        template_views.template_edit,
        name="template-edit",
    ),
    path(
        "przypomnienia/szablony/<int:template_id>/usun/",
        template_views.template_delete,
        name="template-delete",
    ),
    path(
        "przypomnienia/szablony/gotowe/<slug:slug>/zapisz/",
        template_views.template_copy_ready,
        name="template-copy",
    ),
    path(
        "przypomnienia/<int:request_id>/usun/",
        views.request_delete,
        name="delete",
    ),
    path(
        "przypomnienia/<int:request_id>/zapisz-szablon/",
        template_views.template_from_request,
        name="template-from-request",
    ),
    path(
        "przypomnienia/cykliczne/<int:schedule_id>/edytuj/",
        views.recurring_edit,
        name="recurring-edit",
    ),
    path(
        "przypomnienia/cykliczne/<int:schedule_id>/wyslij/",
        views.recurring_send_now,
        name="recurring-send",
    ),
    path(
        "przypomnienia/cykliczne/<int:schedule_id>/wstrzymaj/",
        views.recurring_toggle,
        name="recurring-toggle",
    ),
    path(
        "przypomnienia/cykliczne/<int:schedule_id>/usun/",
        views.recurring_delete,
        name="recurring-delete",
    ),
    path("przypomnienia/<int:request_id>/", views.request_detail, name="detail"),
    path("przypomnienia/<int:request_id>/edytuj/", views.request_edit, name="edit"),
    path("przypomnienia/<int:request_id>/zamknij/", views.request_close, name="close"),
    path(
        "przypomnienia/<int:request_id>/pliki.zip",
        views.request_files_zip,
        name="files-zip",
    ),
]
