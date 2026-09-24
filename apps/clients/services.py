from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Max, Q

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.clients.models import Client
from apps.common.exceptions import NotFoundAppError, ValidationAppError
from apps.requests.models import RequestItem
from apps.requests.services import (
    DELIVERED_STATUSES,
    MISSING_STATUSES,
    NOT_DELIVERED_STATUSES,
)


class ClientStatus(models.TextChoices):
    ACTIVE = "aktywny", "Aktywny"
    MISSING_DOCUMENTS = "brak_dokumentow", "Brak dokumentów"
    ALL_DELIVERED = "wszystko_dostarczone", "Wszystko dostarczone"
    INACTIVE = "nieaktywny", "Nieaktywny"


def with_stats(queryset):
    return queryset.annotate(
        total_items=Count("requests__items", distinct=True),
        delivered_items=Count(
            "requests__items",
            filter=Q(requests__items__status__in=DELIVERED_STATUSES),
            distinct=True,
        ),
        missing_items=Count(
            "requests__items",
            filter=Q(requests__items__status__in=MISSING_STATUSES),
            distinct=True,
        ),
        active_requests=Count(
            "requests",
            filter=Q(requests__items__status__in=NOT_DELIVERED_STATUSES),
            distinct=True,
        ),
        last_activity=Max("requests__updated_at"),
    )


def compute_status(client) -> str:
    if client.total_items == 0:
        return ClientStatus.INACTIVE
    if client.delivered_items == client.total_items:
        return ClientStatus.ALL_DELIVERED
    if client.delivered_items == 0:
        return ClientStatus.MISSING_DOCUMENTS
    return ClientStatus.ACTIVE


CLIENT_SORTS = {
    "name": ("name",),
    "name_desc": ("-name",),
    "activity": (models.F("last_activity").desc(nulls_last=True), "name"),
    "missing": ("-missing_items", "name"),
    "newest": ("-created_at",),
}


class ClientService:
    @staticmethod
    def filter_for_owner(
        owner,
        search=None,
        missing=None,
        activity_from=None,
        activity_to=None,
        sort="name",
    ):
        """Every filter except status, which is computed in Python (see
        compute_status) and therefore applied by the caller."""
        queryset = with_stats(Client.objects.filter(owner=owner)).order_by(
            *CLIENT_SORTS.get(sort, CLIENT_SORTS["name"])
        )
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        if missing == "yes":
            queryset = queryset.filter(missing_items__gt=0)
        elif missing == "no":
            queryset = queryset.filter(missing_items=0)
        if activity_from:
            queryset = queryset.filter(last_activity__date__gte=activity_from)
        if activity_to:
            queryset = queryset.filter(last_activity__date__lte=activity_to)
        results = list(queryset)
        for client in results:
            status = compute_status(client)
            client.status_code = status.value
            client.status_label = status.label
        return results

    @staticmethod
    def list_for_owner(owner, search=None, page=1, page_size=20):
        queryset = with_stats(Client.objects.filter(owner=owner)).order_by("name")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(email__icontains=search)
            )
        paginator = Paginator(queryset, page_size)
        return paginator.get_page(page)

    @staticmethod
    def get_owned_client(owner, client_id):
        client = with_stats(Client.objects.filter(owner=owner, pk=client_id)).first()
        if client is None:
            raise NotFoundAppError("Nie znaleziono klienta.")
        return client

    @staticmethod
    def create(owner, name, email, phone="", note="", request=None):
        client = Client.objects.create(
            owner=owner, name=name, email=email, phone=phone, note=note
        )
        AuditService.log(
            AuditEvent.CLIENT_CREATED, actor=owner, target=client, request=request
        )
        return client

    @staticmethod
    def get_or_create_by_email(owner, email, name="", request=None):
        existing = Client.objects.filter(owner=owner, email__iexact=email).first()
        if existing is not None:
            return existing

        clean_name = name.strip() or email.split("@")[0]
        return ClientService.create(
            owner=owner, name=clean_name, email=email, request=request
        )

    @staticmethod
    def update(client, name, email, phone="", note="", request=None):
        client.name = name
        client.email = email
        client.phone = phone
        client.note = note
        client.save(update_fields=["name", "email", "phone", "note", "updated_at"])
        AuditService.log(
            AuditEvent.CLIENT_UPDATED,
            actor=client.owner,
            target=client,
            request=request,
        )
        return client

    @staticmethod
    def documents(client, status_filter=""):
        queryset = (
            RequestItem.objects.filter(request__client=client)
            .select_related("request")
            .prefetch_related("documents")
            .order_by("-request__created_at", "id")
        )
        if status_filter == "brakujace":
            queryset = queryset.filter(status__in=MISSING_STATUSES)
        elif status_filter == "dostarczone":
            queryset = queryset.filter(status__in=DELIVERED_STATUSES)
        return queryset

    @staticmethod
    def document_counts(client):
        return RequestItem.objects.filter(request__client=client).aggregate(
            all=Count("id"),
            brakujace=Count("id", filter=Q(status__in=MISSING_STATUSES)),
            dostarczone=Count("id", filter=Q(status__in=DELIVERED_STATUSES)),
        )

    @staticmethod
    def delete(client, request=None):
        if client.requests.exists():
            raise ValidationAppError(
                "Nie można usunąć klienta, do którego wysłano prośby o dokumenty.",
                code="CLIENT_HAS_REQUESTS",
            )
        AuditService.log(
            AuditEvent.CLIENT_DELETED,
            actor=client.owner,
            target=client,
            request=request,
        )
        client.delete()
