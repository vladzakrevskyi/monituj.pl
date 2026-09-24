import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.common import legal, throttle
from apps.common.cookies import consent as cookie_consent
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.consents.forms import LegalAcceptanceForm
from apps.consents.models import AcceptanceMethod, CookieConsent
from apps.consents.services import needs_acceptance, record_acceptance

COOKIE_LOGS_PER_IP_HOUR = 60
MAX_BODY = 2048


def _next(request):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("accounts:panel")


@login_required
@require_http_methods(["GET", "POST"])
def accept(request):
    if not needs_acceptance(request.user):
        return redirect(_next(request))
    form = LegalAcceptanceForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            record_acceptance(request.user, AcceptanceMethod.UPDATE, request)
            messages.success(request, "Dziękujemy – nowe dokumenty zaakceptowane.")
            if is_ajax_request(request):
                return success_response({"redirect_url": _next(request)})
            return redirect(_next(request))
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    return render(
        request,
        "consents/accept.html",
        {
            "form": form,
            "next": _next(request),
            "effective_date": legal.effective_date_display(),
        },
    )


@csrf_exempt
@require_POST
def cookie_consent_log(request):
    """Records a cookie banner decision (art. 7(1) RODO: consent must be
    provable). Anonymous and write-only: a random id from the visitor's
    browser, the choice and the banner version - no IP, no account. Needs no
    CSRF token (the banner shows on pages without forms); a forged row only
    adds a meaningless entry, and the rate limit keeps those few."""
    key = throttle.ip_key("cookie-consent", request)
    if throttle.is_limited(key, COOKIE_LOGS_PER_IP_HOUR, throttle.HOUR):
        return HttpResponse(status=429)
    throttle.record(key)
    if len(request.body) > MAX_BODY:
        return HttpResponse(status=400)
    try:
        data = json.loads(request.body)
        consent_id = uuid.UUID(str(data["id"]))
        version = str(data["version"])
        choices = data["choices"]
    except ValueError, KeyError, TypeError:
        return HttpResponse(status=400)
    config = cookie_consent()["config"]
    if (
        version != config["version"]
        or not isinstance(choices, dict)
        or set(choices) != set(config["categories"])
        or not all(isinstance(value, bool) for value in choices.values())
    ):
        return HttpResponse(status=400)
    CookieConsent.objects.create(
        consent_id=consent_id, version=version, choices=choices
    )
    return HttpResponse(status=204)
