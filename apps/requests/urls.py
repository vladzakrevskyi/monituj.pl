from django.urls import path, re_path
from django.views.generic import RedirectView

from apps.requests import question_views, template_views, views

app_name = "requests"

urlpatterns = [
    path("prosby/", views.request_list, name="list"),
    path("zestawienie/", views.overview_view, name="overview"),
    path("zestawienie/przypomnij/", views.overview_remind, name="overview-remind"),
    path("pytania/", question_views.question_list, name="questions"),
    path("pytania/nowe/", question_views.question_create, name="question-create"),
    path("pytania/<int:request_id>/", views.request_detail, name="question-detail"),
    path(
        "prosby/<int:request_id>/notatka/",
        question_views.request_note,
        name="note",
    ),
    path("otrzymane/", views.received_list, name="received"),
    path("prosby/nowe/", views.request_create, name="create"),
    path("prosby/usun/", views.request_bulk_delete, name="bulk-delete"),
    path("prosby/szablony/", template_views.template_list, name="templates"),
    path(
        "prosby/szablony/nowy/",
        template_views.template_create,
        name="template-create",
    ),
    path(
        "prosby/szablony/<int:template_id>/",
        template_views.template_edit,
        name="template-edit",
    ),
    path(
        "prosby/szablony/<int:template_id>/usun/",
        template_views.template_delete,
        name="template-delete",
    ),
    path(
        "prosby/szablony/gotowe/<slug:slug>/zapisz/",
        template_views.template_copy_ready,
        name="template-copy",
    ),
    path(
        "prosby/<int:request_id>/usun/",
        views.request_delete,
        name="delete",
    ),
    path(
        "prosby/<int:request_id>/zapisz-szablon/",
        template_views.template_from_request,
        name="template-from-request",
    ),
    path(
        "prosby/cykliczne/<int:schedule_id>/edytuj/",
        views.recurring_edit,
        name="recurring-edit",
    ),
    path(
        "prosby/cykliczne/<int:schedule_id>/wyslij/",
        views.recurring_send_now,
        name="recurring-send",
    ),
    path(
        "prosby/cykliczne/<int:schedule_id>/wstrzymaj/",
        views.recurring_toggle,
        name="recurring-toggle",
    ),
    path(
        "prosby/cykliczne/<int:schedule_id>/usun/",
        views.recurring_delete,
        name="recurring-delete",
    ),
    path("prosby/<int:request_id>/", views.request_detail, name="detail"),
    path("prosby/<int:request_id>/edytuj/", views.request_edit, name="edit"),
    path("prosby/<int:request_id>/zamknij/", views.request_close, name="close"),
    path("prosby/<int:request_id>/wyslij/", views.request_send_held, name="send-held"),
    path(
        "prosby/<int:request_id>/pliki.zip",
        views.request_files_zip,
        name="files-zip",
    ),
    # The panel used to live under /przypomnienia/ - links in emails sent
    # before the move still work.
    re_path(
        r"^przypomnienia/(?P<rest>.*)$",
        RedirectView.as_view(url="/prosby/%(rest)s", query_string=True, permanent=True),
    ),
]
