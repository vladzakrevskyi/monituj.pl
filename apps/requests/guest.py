"""Sending a request without registering.

The sender gives their email in the public form. Monituj creates (or reuses)
an account without a password for that address, stores the request and asks
the sender to confirm it by email - only then does the recipient hear about
it. From the confirmation on, the sender manages all their requests in the
normal panel, which they open with one permanent link from their inbox."""

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GuestAccess, User
from apps.audit.models import AuditLog
from apps.clients.services import ClientService
from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url
from apps.common.timezones import browser_timezone
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.links import guest_panel_url
from apps.requests.models import Request
from apps.requests.services import (
    CONFIRMATION_TTL,
    RequestService,
    _reserve_daily_anonymous_request_slot,
)

INVALID_LINK_MESSAGE = (
    "Link jest nieprawidłowy lub wygasł. Prośby niepotwierdzone w ciągu 48 godzin "
    "są usuwane – wyślij ją ponownie."
)
SENDER_UNAVAILABLE_MESSAGE = "Z tego adresu nie można wysłać prośby."


def _sender_account(email, display_name, timezone_name=None):
    """The account a public-form request belongs to. A new address gets a
    passwordless account; an existing one (with or without password) is
    reused - which is safe because nothing is sent until the owner of the
    address confirms it."""
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        now = timezone.now()
        user = User.objects.create_user(
            email=email,
            display_name=display_name,
            terms_accepted_at=now,
            privacy_policy_accepted_at=now,
            timezone=timezone_name or settings.TIME_ZONE,
        )
        GuestAccess.objects.create(user=user)
        return user
    if not user.is_active or hasattr(user, "demo_account"):
        raise ValidationAppError(SENDER_UNAVAILABLE_MESSAGE, code="SENDER_UNAVAILABLE")
    if not user.display_name and display_name:
        user.display_name = display_name
        user.save(update_fields=["display_name"])
    return user


class GuestRequestService:
    @staticmethod
    @transaction.atomic
    def submit(form, django_request):
        """Stores the request and mails its sender a confirmation link. The
        IP's daily slot is reserved in the same transaction, so a failure
        below doesn't burn it."""
        _reserve_daily_anonymous_request_slot(django_request)
        data = form.cleaned_data
        owner = _sender_account(
            data["sender_email"], data["sender_name"], browser_timezone(django_request)
        )
        client = ClientService.get_or_create_by_email(
            owner=owner,
            email=data["client_email"],
            name=data["client_name"],
            request=django_request,
        )
        request_obj = RequestService.create(
            owner=owner,
            client_id=client.pk,
            name=data["name"],
            description=data["description"],
            deadline=data["deadline"],
            item_names=form.item_names(),
            password=data["password"],
            reminder_settings=form.request_settings(),
            request=django_request,
            awaiting_confirmation=True,
        )
        confirm_url = absolute_url(
            reverse(
                "public:guest-request-confirm",
                args=[request_obj.confirmation_token],
            )
        )
        EmailService.send(
            EmailTemplate.GUEST_REQUEST_CONFIRM,
            to_email=owner.email,
            context={
                "confirm_url": confirm_url,
                "recipient_name": client.name,
                "recipient_email": client.email,
            },
            request=request_obj,
        )
        return request_obj

    @staticmethod
    def pending(token):
        request_obj = (
            Request.objects.filter(
                confirmation_token=token,
                awaiting_confirmation=True,
                created_at__gte=timezone.now() - CONFIRMATION_TTL,
            )
            .select_related("client", "created_by")
            .first()
        )
        if request_obj is None:
            raise ValidationAppError(INVALID_LINK_MESSAGE, code="INVALID_TOKEN")
        return request_obj

    @staticmethod
    def confirm(token, django_request=None):
        """Sends the request to its recipient. The first confirmation also
        proves the sender's address, so they get their permanent panel link."""
        with transaction.atomic():
            request_obj = GuestRequestService.pending(token)
            request_obj = Request.objects.select_for_update().get(pk=request_obj.pk)
            if not request_obj.awaiting_confirmation:
                raise ValidationAppError(INVALID_LINK_MESSAGE, code="INVALID_TOKEN")
            password = request_obj.pending_access_password
            request_obj.awaiting_confirmation = False
            request_obj.confirmation_token = None
            request_obj.pending_access_password = ""
            request_obj.save(
                update_fields=[
                    "awaiting_confirmation",
                    "confirmation_token",
                    "pending_access_password",
                    "updated_at",
                ]
            )
            owner = request_obj.created_by
            first_confirmation = owner.email_verified_at is None
            if first_confirmation:
                owner.email_verified_at = timezone.now()
                fields = ["email_verified_at"]
                if owner.has_usable_password():
                    # Someone registered this address without ever proving
                    # it; the real owner just did. Their password - and every
                    # session opened with it - stops working.
                    owner.set_unusable_password()
                    fields.append("password")
                owner.save(update_fields=fields)
                GuestAccess.objects.get_or_create(user=owner)

        RequestService.deliver(
            request_obj, password, actor=owner, request=django_request
        )
        if first_confirmation and hasattr(owner, "guest_access"):
            EmailService.send(
                EmailTemplate.GUEST_PANEL_ACCESS,
                to_email=owner.email,
                context={"access_url": guest_panel_url(owner)},
            )
        return request_obj

    @staticmethod
    def delete_unconfirmed(now=None):
        """Drops requests nobody confirmed in time, and the passwordless
        accounts that were created only for them."""
        from apps.accounts.erasure import erase_account

        now = now or timezone.now()
        stale = Request.objects.filter(
            awaiting_confirmation=True, created_at__lt=now - CONFIRMATION_TTL
        )
        count = stale.count()
        request_type = ContentType.objects.get_for_model(Request)
        for request_obj in stale.select_related("client"):
            client = request_obj.client
            AuditLog.objects.filter(
                content_type=request_type, object_id=request_obj.pk
            ).delete()
            request_obj.delete()
            if not client.requests.exists():
                client.delete()

        orphans = User.objects.filter(
            guest_access__isnull=False,
            email_verified_at__isnull=True,
            date_joined__lt=now - CONFIRMATION_TTL,
            requests__isnull=True,
        )
        for user in orphans:
            erase_account(user)
        return count
