from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.legal import legal_context
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.contact.forms import ContactForm
from apps.contact.services import ContactService

SENT_TITLE = "Dziękujemy za wiadomość"
SENT_MESSAGE = (
    "Odpowiemy najszybciej, jak to możliwe. Potwierdzenie otrzymania "
    "wysłaliśmy na Twój adres email."
)


@require_http_methods(["GET", "POST"])
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            try:
                ContactService.send(form, request)
                if is_ajax_request(request):
                    return success_response(
                        {"title": SENT_TITLE, "message": SENT_MESSAGE}
                    )
                messages.success(request, SENT_MESSAGE)
                return redirect("pages:contact")
            except ApplicationError as exc:
                add_service_error(form, exc)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = ContactForm()
    return render(
        request, "pages/contact.html", {"form": form, "legal": legal_context()}
    )
