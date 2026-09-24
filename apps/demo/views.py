from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.common.exceptions import RateLimitedAppError
from apps.demo.models import is_demo_user
from apps.demo.services import DemoService


@require_POST
def start(request):
    if request.user.is_authenticated:
        # A real account is never swapped for a demo one behind the user's back.
        return redirect("accounts:panel")
    try:
        DemoService.start(request)
    except RateLimitedAppError as exc:
        messages.error(request, exc.message)
        return redirect("pages:demo")
    messages.success(
        request,
        "Witaj w wersji demo! Wszystkie dane są przykładowe, a emaile nie są wysyłane.",
    )
    return redirect("accounts:panel")


@require_POST
def end(request):
    if is_demo_user(request.user):
        user = request.user
        logout(request)
        DemoService.delete(user)
        messages.success(
            request, "Demo zakończone, dane zostały usunięte. Załóż własne konto."
        )
    return redirect("accounts:register")
