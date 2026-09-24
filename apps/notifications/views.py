from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from apps.notifications import inbox


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
