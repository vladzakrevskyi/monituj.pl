from django.urls import path

from apps.common import legal

app_name = "legal"

urlpatterns = [
    path("regulamin/", legal.terms, name="terms"),
    path("polityka-prywatnosci/", legal.privacy, name="privacy"),
    path("polityka-cookies/", legal.cookies, name="cookies"),
    path("umowa-powierzenia/", legal.dpa, name="dpa"),
]
