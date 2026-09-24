from django.urls import path

from apps.requests import views

app_name = "requests"

urlpatterns = [
    path("przypomnienia/", views.request_list, name="list"),
    path("przypomnienia/nowe/", views.request_create, name="create"),
    path("przypomnienia/<int:request_id>/", views.request_detail, name="detail"),
    path("przypomnienia/<int:request_id>/edytuj/", views.request_edit, name="edit"),
    path("przypomnienia/<int:request_id>/zamknij/", views.request_close, name="close"),
]
