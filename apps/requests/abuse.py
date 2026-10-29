""" "Zgłoś nadużycie": a recipient who thinks a request is a fraud - someone
posing as a bank or an office, asking for codes or passwords - says so in
one click from the email or the request's page. Every report is an alarm
to SECURITY_EMAIL at once (with how many reports the same account already
has); nothing is blocked automatically - the team decides (admin →
Zgłoszenia nadużyć)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.common import security_watch, throttle
from apps.common.site import absolute_url
from apps.requests.models import AbuseReport

REPORTS_PER_IP_HOUR = 5
KEPT_FOR = timedelta(days=365)
DETAILS_LENGTH = 1000


def report_url(request_obj):
    return absolute_url(reverse("public:report-abuse", args=[request_obj.public_token]))


def report(request_obj, reason, details, django_request):
    throttle.consume(
        throttle.ip_key("abuse-report", django_request),
        REPORTS_PER_IP_HOUR,
        throttle.HOUR,
        "Wysłano już kilka zgłoszeń. Spróbuj ponownie za godzinę albo napisz do nas.",
        code="REPORT_LIMIT_REACHED",
    )
    owner = request_obj.created_by
    found = AbuseReport.objects.create(
        request=request_obj,
        sender_email=owner.email,
        recipient_email=request_obj.client.email,
        reason=reason,
        details=details.strip()[:DETAILS_LENGTH],
    )
    earlier = AbuseReport.objects.filter(sender_email__iexact=owner.email).count() - 1
    security_watch.alert(
        f"zgłoszenie nadużycia: {owner.email}",
        [
            f"Powód: {found.get_reason_display()}",
            f"Opis: {found.details or '(brak)'}",
            f"Prośba: #{request_obj.pk} „{request_obj.name}”",
            f"Nadawca: {owner.display_name or '(bez nazwy)'} <{owner.email}>",
            f"Odbiorca (zgłaszający): {request_obj.client.email}",
            f"Wcześniejsze zgłoszenia tego konta: {earlier}",
            "",
            "Sprawdź prośbę w panelu administratora. Jeśli to oszustwo: zamknij "
            "prośby konta i zablokuj je (Użytkownicy → aktywny: nie).",
        ],
        key=f"abuse-report:{found.pk}",
        advice="",
    )
    return found


def delete_old():
    return AbuseReport.objects.filter(
        created_at__lt=timezone.now() - KEPT_FOR
    ).delete()[0]
