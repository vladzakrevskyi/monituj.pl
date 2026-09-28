from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("plan/", views.plan_view, name="plan"),
    path("plan/zamow/", views.checkout, name="checkout"),
    path("plan/zmien/", views.change, name="change"),
    path("plan/platnosci/", views.portal, name="portal"),
    path("plan/potwierdzenie/", views.checkout_return, name="return"),
    path("plan/dane/", views.billing_profile, name="profile"),
    path("plan/dane/rejestr/", views.registry_lookup, name="registry"),
    path(
        "plan/faktury/<int:invoice_id>/pdf/",
        views.invoice_pdf,
        name="invoice-pdf",
    ),
    path("stripe/webhook/", views.webhook, name="webhook"),
    path("infakt/webhook/", views.infakt_webhook, name="infakt-webhook"),
]
