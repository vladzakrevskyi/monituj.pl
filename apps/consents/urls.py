from django.urls import path

from apps.consents import views

app_name = "consents"

urlpatterns = [
    path("akceptacja-dokumentow/", views.accept, name="accept"),
    path("api/cookie-consent/", views.cookie_consent_log, name="cookie-consent"),
]
