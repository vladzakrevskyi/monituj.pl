"""The Django admin can change any account, so:
- ADMIN_ALLOWED_IPS: only these addresses reach it at all; everyone else
  gets a plain 404, as if there were no admin (checked here in the app, so
  it holds whatever the nginx config says and wherever ADMIN_URL points);
- its login gets the same protection as the site's: a limit on failed
  attempts per address and per login name, every failure in the audit log,
  and the code from the app for accounts with two-step verification.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.auth import logout as django_logout
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts import two_factor
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common import throttle
from apps.common.maintenance import is_allowed, parse_networks
from apps.common.security import get_client_ip, hash_token

FAILURES_PER_IP = 10
FAILURES_PER_LOGIN = 5
WINDOW = timedelta(minutes=15)
BLOCKED_MESSAGE = "Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za 15 minut."


def admin_login(request, extra_context=None):
    if request.method != "POST":
        return admin.site.login(request, extra_context)
    login = request.POST.get("username", "").strip().lower()
    ip_key = throttle.ip_key("admin-login-ip", request)
    login_key = "admin-login:" + hash_token(login)
    if throttle.is_limited(ip_key, FAILURES_PER_IP, WINDOW) or throttle.is_limited(
        login_key, FAILURES_PER_LOGIN, WINDOW
    ):
        return HttpResponse(BLOCKED_MESSAGE, status=429, content_type="text/plain")
    response = admin.site.login(request, extra_context)
    user = request.user
    if user.is_authenticated and user.is_active and user.is_staff:
        throttle.clear(login_key)
        if two_factor.needs_code(request, user):
            # The password was right; the code comes before the admin opens.
            backend = request.session[BACKEND_SESSION_KEY]
            next_url = request.POST.get("next") or reverse("admin:index")
            django_logout(request)
            two_factor.hold(request, user, backend, "admin", next_url)
            return redirect("accounts:two-factor-login")
        return response
    throttle.record(ip_key)
    throttle.record(login_key)
    AuditService.log(
        AuditEvent.USER_LOGIN_FAILED,
        request=request,
        metadata={"email": login, "admin": True},
    )
    return response


class AdminAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.prefix = f"/{settings.ADMIN_URL}"
        self.networks = parse_networks(
            settings.ADMIN_ALLOWED_IPS, setting="ADMIN_ALLOWED_IPS"
        )

    def __call__(self, request):
        if (
            self.networks
            and request.path.startswith(self.prefix)
            and not is_allowed(get_client_ip(request), self.networks)
        ):
            raise Http404
        return self.get_response(request)
