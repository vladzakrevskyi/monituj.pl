from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import is_guest_account
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.clients.models import Client
from apps.common.exceptions import (
    NotFoundAppError,
    RateLimitedAppError,
    ValidationAppError,
)
from apps.common.security import generate_public_token, get_client_ip, hash_ip
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.models import (
    AnonymousRequestThrottle,
    PasswordProtectedAccess,
    Request,
    RequestItem,
    RequestItemStatus,
)

DAILY_LIMIT_MESSAGE = (
    "Dzisiaj można wysłać tylko jedną prośbę bez konta. "
    "Spróbuj ponownie jutro albo załóż konto, aby wysyłać prośby bez limitu."
)
GUEST_DAILY_LIMIT_MESSAGE = (
    "Z tego adresu wysłano już dziś prośbę bez hasła. Jutro możesz wysłać "
    "kolejną – albo ustaw hasło w ustawieniach konta, aby wysyłać bez limitu."
)
CLOSED_MESSAGE = "Ta prośba została zamknięta – nie można już przesyłać plików."
# How long a request sent through the public form waits for its sender to
# confirm it before it is deleted.
CONFIRMATION_TTL = timedelta(hours=48)

DELIVERED_STATUSES = [RequestItemStatus.DOSTARCZONY, RequestItemStatus.ZAAKCEPTOWANY]
MISSING_STATUSES = [RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY]
NOT_DELIVERED_STATUSES = [
    RequestItemStatus.BRAK,
    RequestItemStatus.W_TRAKCIE,
    RequestItemStatus.ODRZUCONY,
]


class RequestStatus(models.TextChoices):
    MISSING = "brak_dokumentow", "Brak dokumentów"
    IN_PROGRESS = "w_trakcie", "W trakcie"
    COMPLETE = "kompletny", "Kompletny"
    OVERDUE = "po_terminie", "Po terminie"
    CLOSED = "zamkniety", "Zamknięta"
    AWAITING = "niepotwierdzony", "Czeka na potwierdzenie"


def with_stats(queryset):
    return queryset.annotate(
        total_items=Count("items", distinct=True),
        delivered_items=Count(
            "items", filter=Q(items__status__in=DELIVERED_STATUSES), distinct=True
        ),
    )


def compute_status(request) -> str:
    if request.awaiting_confirmation:
        return RequestStatus.AWAITING
    if request.closed_at:
        return RequestStatus.CLOSED
    is_complete = (
        request.total_items > 0 and request.delivered_items == request.total_items
    )
    if is_complete:
        return RequestStatus.COMPLETE
    if request.deadline and request.deadline < timezone.now():
        return RequestStatus.OVERDUE
    if request.delivered_items == 0:
        return RequestStatus.MISSING
    return RequestStatus.IN_PROGRESS


def _reserve_daily_anonymous_request_slot(django_request) -> None:
    ip = get_client_ip(django_request)
    try:
        with transaction.atomic():
            AnonymousRequestThrottle.objects.create(
                ip_hash=hash_ip(ip), throttle_date=timezone.localdate()
            )
    except IntegrityError as exc:
        raise RateLimitedAppError(
            DAILY_LIMIT_MESSAGE, code="DAILY_LIMIT_REACHED"
        ) from exc


def check_guest_daily_limit(owner) -> None:
    """Accounts without a password may send one request a day."""
    today_start = timezone.localtime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if Request.objects.filter(created_by=owner, created_at__gte=today_start).exists():
        raise RateLimitedAppError(
            GUEST_DAILY_LIMIT_MESSAGE, code="GUEST_DAILY_LIMIT_REACHED"
        )


REQUEST_SORTS = {
    "newest": ("-created_at",),
    "oldest": ("created_at",),
    "deadline": (models.F("deadline").asc(nulls_last=True), "-created_at"),
    "name": ("name",),
}


class RequestService:
    @staticmethod
    def filter_for_owner(
        owner,
        search=None,
        client_id=None,
        deadline_from=None,
        deadline_to=None,
        reminders=None,
        sort="newest",
    ):
        """Every filter except status, which is computed per request in Python
        (see compute_status) and therefore applied by the caller."""
        queryset = with_stats(
            Request.objects.filter(created_by=owner).select_related("client")
        ).order_by(*REQUEST_SORTS.get(sort, REQUEST_SORTS["newest"]))
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(client__name__icontains=search)
                | Q(client__email__icontains=search)
            )
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        if deadline_from:
            queryset = queryset.filter(deadline__date__gte=deadline_from)
        if deadline_to:
            queryset = queryset.filter(deadline__date__lte=deadline_to)
        if reminders == "on":
            queryset = queryset.filter(reminders_enabled=True)
        elif reminders == "off":
            queryset = queryset.filter(reminders_enabled=False)
        results = list(queryset)
        for request_obj in results:
            request_obj.status_code = compute_status(request_obj)
        return results

    @staticmethod
    def list_for_owner(owner, search=None, status_filter=None, page=1, page_size=20):
        results = RequestService.filter_for_owner(owner, search=search)
        if status_filter:
            results = [r for r in results if r.status_code == status_filter]
        paginator = Paginator(results, page_size)
        return paginator.get_page(page)

    @staticmethod
    def get_owned_request(owner, request_id):
        request_obj = with_stats(
            Request.objects.filter(created_by=owner, pk=request_id).select_related(
                "client"
            )
        ).first()
        if request_obj is None:
            raise NotFoundAppError("Nie znaleziono prośby.")
        return request_obj

    @staticmethod
    @transaction.atomic
    def create(
        owner,
        client_id,
        name,
        description,
        deadline,
        item_names,
        password=None,
        reminder_settings=None,
        request=None,
        awaiting_confirmation=False,
    ):
        """awaiting_confirmation=True stores the request without contacting
        the recipient; GuestRequestService.confirm() sends it later."""
        if is_guest_account(owner):
            check_guest_daily_limit(owner)
        client = Client.objects.filter(owner=owner, pk=client_id).first()
        if client is None:
            raise NotFoundAppError("Nie znaleziono klienta.")

        clean_item_names = [n.strip() for n in item_names if n.strip()]
        if not clean_item_names:
            raise ValidationAppError("Dodaj co najmniej jeden dokument do listy.")

        reminder_settings = reminder_settings or {}
        request_obj = Request.objects.create(
            client=client,
            created_by=owner,
            name=name,
            description=description,
            deadline=deadline,
            awaiting_confirmation=awaiting_confirmation,
            confirmation_token=(
                generate_public_token() if awaiting_confirmation else None
            ),
            pending_access_password=(password or "") if awaiting_confirmation else "",
            **reminder_settings,
        )
        RequestItem.objects.bulk_create(
            [
                RequestItem(request=request_obj, name=item_name)
                for item_name in clean_item_names
            ]
        )
        if password:
            PasswordProtectedAccess.objects.create(
                request=request_obj, password_hash=make_password(password)
            )

        AuditService.log(
            AuditEvent.REQUEST_CREATED, actor=owner, target=request_obj, request=request
        )
        if not awaiting_confirmation:
            RequestService.deliver(request_obj, password, actor=owner, request=request)
        return request_obj

    @staticmethod
    def deliver(request_obj, password, actor=None, request=None):
        """Sends the recipient their link (and the access password, if any)."""
        RequestService.send_invitation(
            request_obj, request_obj.client.email, actor=actor, django_request=request
        )
        if password:
            EmailService.send(
                EmailTemplate.ACCESS_PASSWORD,
                to_email=request_obj.client.email,
                context={"request_name": request_obj.name, "password": password},
                request=request_obj,
            )

    @staticmethod
    def close(request_obj, actor, request=None):
        if request_obj.closed_at is None:
            request_obj.closed_at = timezone.now()
            request_obj.save(update_fields=["closed_at", "updated_at"])
            AuditService.log(
                AuditEvent.REQUEST_CLOSED,
                actor=actor,
                target=request_obj,
                request=request,
            )
        return request_obj

    @staticmethod
    def reopen(request_obj, actor, request=None):
        if request_obj.closed_at is not None:
            request_obj.closed_at = None
            request_obj.save(update_fields=["closed_at", "updated_at"])
            AuditService.log(
                AuditEvent.REQUEST_REOPENED,
                actor=actor,
                target=request_obj,
                request=request,
            )
        return request_obj

    @staticmethod
    def send_invitation(request_obj, to_email, actor=None, django_request=None):
        link = absolute_url(f"/d/{request_obj.public_token}/")
        EmailService.send(
            EmailTemplate.INVITATION,
            to_email=to_email,
            context={
                "request_name": request_obj.name,
                "link": link,
                "deadline": request_obj.deadline,
                "password_protected": request_obj.is_password_protected,
            },
            request=request_obj,
        )
        AuditService.log(
            AuditEvent.INVITATION_SENT,
            actor=actor,
            target=request_obj,
            request=django_request,
        )

    @staticmethod
    def update(
        request_obj, name, description, deadline, reminder_settings=None, request=None
    ):
        request_obj.name = name
        request_obj.description = description
        request_obj.deadline = deadline
        for field, value in (reminder_settings or {}).items():
            setattr(request_obj, field, value)
        request_obj.save()
        AuditService.log(
            AuditEvent.REQUEST_UPDATED,
            actor=request_obj.created_by,
            target=request_obj,
            request=request,
        )
        return request_obj


class PublicAccessService:
    @staticmethod
    def get_by_token(token):
        request_obj = with_stats(
            Request.objects.filter(
                public_token=token, awaiting_confirmation=False
            ).select_related("client", "created_by")
        ).first()
        if request_obj is None:
            raise NotFoundAppError("Nie znaleziono zasobu.")
        return request_obj

    @staticmethod
    def session_key(request_obj):
        return f"granted_request_{request_obj.pk}"

    @staticmethod
    def has_access(request_obj, django_request):
        """Whether this session has actually been granted access to this
        specific request (i.e. previously proved knowledge of its public
        token). Never inferred purely from the request's protection state,
        since document IDs are sequential and guessable (§7/§33)."""
        return bool(
            django_request.session.get(PublicAccessService.session_key(request_obj))
        )

    @staticmethod
    def grant_access(request_obj, django_request):
        if not django_request.session.session_key:
            django_request.session.save()
        django_request.session[PublicAccessService.session_key(request_obj)] = True

    @staticmethod
    def check_password(request_obj, raw_password, django_request):
        access = request_obj.password_protected_access
        if not check_password(raw_password, access.password_hash):
            AuditService.log(
                AuditEvent.PASSWORD_ACCESS_FAILED,
                target=request_obj,
                request=django_request,
            )
            return False
        PublicAccessService.grant_access(request_obj, django_request)
        return True

    @staticmethod
    def mark_accessed(request_obj, django_request):
        AuditService.log(
            AuditEvent.PUBLIC_LINK_ACCESSED, target=request_obj, request=django_request
        )


class DashboardService:
    @staticmethod
    def for_owner(owner):
        from django.contrib.contenttypes.models import ContentType

        from apps.audit.models import AuditLog
        from apps.audit.services import translate_event
        from apps.reminders.models import Reminder

        requests_qs = Request.objects.filter(created_by=owner)
        request_ids = list(requests_qs.values_list("pk", flat=True))

        item_stats = RequestItem.objects.filter(request_id__in=request_ids).aggregate(
            missing=Count("id", filter=Q(status__in=MISSING_STATUSES)),
            delivered=Count("id", filter=Q(status__in=DELIVERED_STATUSES)),
        )

        annotated = list(with_stats(requests_qs))
        finished = (
            RequestStatus.COMPLETE,
            RequestStatus.CLOSED,
            RequestStatus.AWAITING,
        )
        active_requests = sum(1 for r in annotated if compute_status(r) not in finished)

        reminders_sent = Reminder.objects.filter(request_id__in=request_ids).count()

        recent_activity = list(
            AuditLog.objects.filter(
                Q(actor=owner)
                | Q(
                    content_type=ContentType.objects.get_for_model(Request),
                    object_id__in=request_ids,
                )
            )
            .select_related("actor")
            .order_by("-created_at")[:10]
        )
        for entry in recent_activity:
            entry.label_pl = translate_event(entry.event)

        return {
            "active_requests": active_requests,
            "missing_documents": item_stats["missing"] or 0,
            "delivered_documents": item_stats["delivered"] or 0,
            "reminders_sent": reminders_sent,
            "recent_activity": recent_activity,
        }
