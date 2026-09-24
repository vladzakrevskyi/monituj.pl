from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from apps.common.responses import error_response
from apps.consents.services import needs_acceptance

# The working part of the panel. Settings stay open (so someone who doesn't
# accept can still delete the account), and so do logging out, the
# documents themselves and everything public.
GATED_NAMESPACES = {
    "clients",
    "requests",
    "notifications",
    "clients_api",
    "requests_api",
    "reminders_api",
}
GATED_VIEWS = {
    ("accounts", "panel"),
    ("documents_api", "download"),
    ("documents_api", "accept-item"),
    ("documents_api", "reject-item"),
}
MESSAGE = (
    "Zaktualizowaliśmy Regulamin i Politykę prywatności. Zaakceptuj je, "
    "aby dalej korzystać z panelu."
)


class LegalAcceptanceMiddleware:
    """After the documents change, the panel waits until the new version is
    accepted - that acceptance is recorded like the first one."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match is None or not request.user.is_authenticated:
            return None
        gated = match.namespace in GATED_NAMESPACES or (
            (match.namespace, match.url_name) in GATED_VIEWS
        )
        if not gated or not needs_acceptance(request.user):
            return None
        if request.path.startswith("/api/"):
            return error_response("LEGAL_ACCEPTANCE_REQUIRED", MESSAGE, status=403)
        target = reverse("consents:accept")
        if request.method == "GET":
            target += "?" + urlencode({"next": request.get_full_path()})
        return redirect(target)
