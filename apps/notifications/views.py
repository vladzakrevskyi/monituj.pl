from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.notifications import inbox, reviews
from apps.notifications.models import ReviewInvite


@login_required
def notification_list(request):
    page_obj = Paginator(inbox.for_user(request.user), 30).get_page(
        request.GET.get("page", 1)
    )
    # Rendered before marking, so what's new is still highlighted this time.
    response = render(
        request,
        "notifications/list.html",
        {"page_obj": page_obj, "notices": list(page_obj.object_list)},
    )
    inbox.mark_read(request.user)
    return response


# --- "Oceń Monituj" emails (apps/notifications/reviews.py) ------------------------


def review(request, token):
    """The email's button: noted as done, then on to Trustpilot. A link
    from an old or unknown email still leads there."""
    ReviewInvite.objects.filter(token=token, clicked_at__isnull=True).update(
        clicked_at=timezone.now()
    )
    return redirect(reviews.trustpilot_url())


@csrf_exempt  # the token is the proof; mail apps unsubscribe with a bare POST
@require_http_methods(["GET", "POST"])
def review_stop(request, token):
    """ "Nie chcę takich wiadomości": a page with one button - a GET alone
    changes nothing, since mail scanners open links. The mail app's own
    "Wypisz się" POSTs here directly (List-Unsubscribe-Post)."""
    done = request.method == "POST"
    if done:
        ReviewInvite.objects.filter(token=token, declined_at__isnull=True).update(
            declined_at=timezone.now()
        )
    response = render(request, "notifications/review_stop.html", {"done": done})
    response["X-Robots-Tag"] = "noindex"
    return response
