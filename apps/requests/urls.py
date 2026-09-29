from django.urls import path

from apps.requests import views

app_name = "requests"

urlpatterns = [
    path("przypomnienia/", views.request_list, name="list"),
    path("otrzymane/", views.received_list, name="received"),
    path("przypomnienia/nowe/", views.request_create, name="create"),
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
