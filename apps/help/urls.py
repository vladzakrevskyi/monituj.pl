from django.urls import path

from apps.help import views

app_name = "help"

urlpatterns = [
    path("pomoc/", views.index, name="index"),
    path("pomoc/szukaj/", views.search_view, name="search"),
    path("pomoc/temat/<slug:slug>/", views.category, name="category"),
    path("pomoc/<slug:slug>/", views.article, name="article"),
]
