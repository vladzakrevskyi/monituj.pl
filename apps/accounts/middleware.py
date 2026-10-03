from django.contrib import messages
from django.shortcuts import redirect, render

from apps.accounts import team
from apps.common.responses import error_response

# What still works inside a team workspace whose access waits: switching
# away, the personal settings (to leave the team) and signing out.
OPEN_FOR_PAUSED = {
    ("accounts", "logout"),
    ("accounts", "settings"),
    ("accounts", "two-factor"),
    ("accounts", "team-leave"),
    ("accounts", "workspace"),
}
PANEL_NAMESPACES = {
    "accounts",
    "clients",
    "requests",
    "notifications",
    "billing",
    "clients_api",
    "requests_api",
    "reminders_api",
    "documents_api",
}
# Recipients' side of the documents API - not the panel.
PUBLIC_VIEWS = {"upload", "public-delete", "public-not-applicable", "download"}
PAUSED_MESSAGE = (
    "Twój dostęp do tego zespołu jest wstrzymany - plan obejmuje mniej osób. "
    "Poproś właściciela konta o zmianę planu albo przełącz się na inne konto."
)


class WorkspaceMiddleware:
    """request.account: whose data the panel works with - the user's own
    account or a team they belong to (apps/accounts/team.py); and
    request.membership in a team. Members whose access waits stay outside
    that workspace, and the plan, the team and payments are the owner's."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.account = None
        request.membership = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.account, request.membership = team.resolve(request)
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        found = getattr(request, "membership", None)
        if match is None or found is None or match.namespace not in PANEL_NAMESPACES:
            return None
        if (match.namespace, match.url_name) in OPEN_FOR_PAUSED:
            return None
        if match.namespace == "documents_api" and match.url_name in PUBLIC_VIEWS:
            return None
        if not team.has_access(found):
            if request.path.startswith("/api/"):
                return error_response("TEAM_ACCESS_PAUSED", PAUSED_MESSAGE, status=403)
            return render(
                request,
                "accounts/team_paused.html",
                {"firm": team.firm_name(found.owner)},
                status=403,
            )
        if match.namespace == "billing" or match.url_name == "team":
            messages.info(
                request,
                "Tym zarządza właściciel konta zespołu. Twój plan i zespół "
                "znajdziesz na swoim koncie.",
            )
            return redirect("accounts:panel")
        return None
