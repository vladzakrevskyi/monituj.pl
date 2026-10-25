"""The calendar page, "Przypomnij mi", the morning email switch and the
calendar feed for a phone (apps/agenda)."""

from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.agenda import calendar, ics
from apps.agenda.models import AgendaSettings, PersonalReminder, settings_for
from apps.clients.models import Client
from apps.common import throttle

MAX_TEXT = 300
# Calendar apps check a feed every few hours; this is far above that.
FEED_PER_IP_HOUR = 120


class ReminderForm(forms.Form):
    text = forms.CharField(
        label="Przypomnij mi",
        max_length=MAX_TEXT,
        error_messages={
            "required": "Napisz, o czym przypomnieć.",
            "max_length": f"Najwyżej {MAX_TEXT} znaków.",
        },
    )
    due_on = forms.DateField(
        label="Dnia",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={
            "required": "Wybierz dzień.",
            "invalid": "Podaj poprawną datę.",
        },
    )
    client = forms.ModelChoiceField(
        label="Klient (opcjonalnie)",
        queryset=Client.objects.none(),
        required=False,
        empty_label="Bez klienta",
    )

    def __init__(self, *args, account=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(owner=account).order_by(
            "name"
        )


def _back(request, fallback="agenda:calendar"):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback)


def _month_asked(value):
    try:
        year, number = (int(part) for part in (value or "").split("-"))
        date(year, number, 1)
        return year, number
    except ValueError, TypeError:
        today = timezone.localdate()
        return today.year, today.month


@login_required
def calendar_page(request):
    year, number = _month_asked(request.GET.get("m"))
    agenda = settings_for(request.user)
    feed_url = (
        request.build_absolute_uri(f"/kalendarz/ics/{agenda.feed_token}.ics")
        if agenda.feed_token
        else ""
    )
    return render(
        request,
        "agenda/calendar.html",
        {
            "month": calendar.month(request.account, year, number),
            "summary": calendar.today_summary(request.account, request.user),
            "form": ReminderForm(
                account=request.account,
                initial={"due_on": timezone.localdate()},
            ),
            "agenda": agenda,
            "feed_url": feed_url,
            "webcal_url": feed_url.replace("https://", "webcal://", 1).replace(
                "http://", "webcal://", 1
            ),
        },
    )


@login_required
@require_POST
def reminder_add(request):
    form = ReminderForm(request.POST, account=request.account)
    if form.is_valid():
        PersonalReminder.objects.create(
            account=request.account,
            author=request.user,
            client=form.cleaned_data["client"],
            text=" ".join(form.cleaned_data["text"].split()),
            due_on=form.cleaned_data["due_on"],
        )
        messages.success(
            request,
            f"Przypomnimy {form.cleaned_data['due_on']:%d.%m.%Y} - w kalendarzu "
            "i w porannym e-mailu.",
        )
    else:
        messages.error(request, next(iter(form.errors.values()))[0])
    return _back(request)


def _own_reminder(request, reminder_id):
    reminder = PersonalReminder.objects.filter(
        pk=reminder_id, account=request.account
    ).first()
    if reminder is None:
        raise Http404
    return reminder


@login_required
@require_POST
def reminder_done(request, reminder_id):
    reminder = _own_reminder(request, reminder_id)
    reminder.done_at = None if reminder.done_at else timezone.now()
    reminder.save(update_fields=["done_at"])
    return _back(request)


@login_required
@require_POST
def reminder_delete(request, reminder_id):
    _own_reminder(request, reminder_id).delete()
    messages.success(request, "Przypomnienie usunięte.")
    return _back(request)


@login_required
@require_POST
def daily_email(request):
    agenda = settings_for(request.user)
    agenda.daily_email = request.POST.get("daily_email") == "on"
    agenda.save(update_fields=["daily_email"])
    messages.success(
        request,
        "Poranny e-mail „Na dziś” włączony."
        if agenda.daily_email
        else "Poranny e-mail „Na dziś” wyłączony.",
    )
    return redirect("agenda:calendar")


@login_required
@require_POST
def feed_link(request):
    """A new secret link for the calendar feed; the old one stops working."""
    settings_for(request.user).new_feed_token()
    messages.success(
        request,
        "Gotowe. Skopiuj link i dodaj go w kalendarzu Google, Outlooku albo "
        "iPhone'a jako subskrypcję.",
    )
    return redirect("agenda:calendar")


@require_GET
def feed(request, token):
    """The .ics feed - by the secret link alone, as calendar apps fetch it."""
    key = throttle.ip_key("calendar-feed", request)
    if throttle.is_limited(key, FEED_PER_IP_HOUR, throttle.HOUR):
        return HttpResponse("Zbyt wiele pobrań kalendarza.", status=429)
    throttle.record(key)
    agenda = (
        AgendaSettings.objects.filter(feed_token=token).select_related("user").first()
    )
    if agenda is None or not agenda.user.is_active:
        raise Http404
    body = ics.feed_for(agenda.user, request.build_absolute_uri("/"))
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Cache-Control"] = "private, max-age=900"
    return response
