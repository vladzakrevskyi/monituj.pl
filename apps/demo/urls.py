from django.urls import path

from apps.demo import views

app_name = "demo"

urlpatterns = [
    path("demo/start/", views.start, name="start"),
    path("demo/zakoncz/", views.end, name="end"),
]
