from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.common.exceptions import RateLimitedAppError
from apps.demo.models import is_demo_user
from apps.demo.services import RESUME_COOKIE, DemoService


@require_POST
def start(request):
    if request.user.is_authenticated:
        # A real account is never swapped for a demo one behind the user's back.
        return redirect("accounts:panel")
    user = DemoService.resume(request)
    if user is not None:
        # Their demo is still running - back to it, no new one.
        messages.success(request, "Wracasz do swojej wersji demo.")
        return redirect("accounts:panel")
    try:
        user = DemoService.start(request)
    except RateLimitedAppError as exc:
        messages.error(request, exc.message)
        return redirect("pages:demo")
    messages.success(
        request,
        "Witaj w wersji demo! Wszystkie dane są przykładowe, a emaile nie są wysyłane.",
    )
    response = redirect("accounts:panel")
    value, expires = DemoService.resume_cookie(user)
    response.set_cookie(
        RESUME_COOKIE,
        value,
        expires=expires,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )
    return response


@require_POST
def end(request):
    if is_demo_user(request.user):
        user = request.user
        logout(request)
        DemoService.delete(user)
        messages.success(
            request, "Demo zakończone, dane zostały usunięte. Załóż własne konto."
        )
    response = redirect("accounts:register")
    response.delete_cookie(RESUME_COOKIE)
    return response
