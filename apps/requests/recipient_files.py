"""The recipient came back from another device (or after the session
expired) and wants to see the files they sent. A request link alone shows
only files sent from this browser - links get forwarded. So we mail a link
to the address the request was sent to; opening it makes this browser count
as the recipient (like signing in to their account): all their files, no
request password.
"""

from django.core import signing
from django.urls import reverse

from apps.common import throttle
from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.received import mark_verified_recipient
from apps.requests.services import PublicAccessService

SALT = "recipient-files"
LINK_MAX_AGE = 60 * 60  # an hour
LINKS_PER_REQUEST_HOUR = 3
LINKS_PER_IP_HOUR = 10
INVALID_MESSAGE = (
    "Link jest nieprawidłowy albo wygasł (działa przez godzinę). Wróć do prośby "
    "i poproś o nowy."
)


def send_link(request_obj, django_request):
    throttle.consume(
        throttle.ip_key("recipient-files", django_request),
        LINKS_PER_IP_HOUR,
        throttle.HOUR,
        "Wysłaliśmy już kilka linków. Spróbuj ponownie za godzinę.",
        code="RECIPIENT_LINK_LIMIT",
    )
    key = f"recipient-files:{request_obj.pk}"
    if throttle.is_limited(key, LINKS_PER_REQUEST_HOUR, throttle.HOUR):
        return  # quietly: an earlier email is on its way
    throttle.record(key)
    signed = signing.dumps(
        {"r": request_obj.pk, "e": request_obj.client.email.strip().lower()},
        salt=SALT,
    )
    url = absolute_url(
        reverse(
            "public:recipient-files-confirm",
            args=[request_obj.public_token, signed],
        )
    )
    # Always the request's own recipient - never an address typed in here.
    EmailService.send(
        EmailTemplate.RECIPIENT_FILES_LINK,
        to_email=request_obj.client.email,
        context={"confirm_url": url},
        request=request_obj,
    )


def check_link(token, signed):
    request_obj = PublicAccessService.get_by_token(token)
    try:
        data = signing.loads(signed, salt=SALT, max_age=LINK_MAX_AGE)
    except signing.BadSignature as exc:
        raise ValidationAppError(INVALID_MESSAGE, code="INVALID_TOKEN") from exc
    # Bound to this request and to the address it was sent to right now.
    if (
        data.get("r") != request_obj.pk
        or data.get("e") != request_obj.client.email.strip().lower()
    ):
        raise ValidationAppError(INVALID_MESSAGE, code="INVALID_TOKEN")
    return request_obj


def confirm(token, signed, django_request):
    request_obj = check_link(token, signed)
    mark_verified_recipient(django_request, request_obj.client.email)
    PublicAccessService.grant_access(request_obj, django_request)
    return request_obj
