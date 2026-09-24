from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from apps.audit.models import AuditEvent, AuditLog

EVENT_LABELS_PL = {
    AuditEvent.USER_REGISTERED: "Zarejestrowano konto",
    AuditEvent.USER_LOGIN: "Zalogowano się",
    AuditEvent.USER_LOGIN_FAILED: "Nieudana próba logowania",
    AuditEvent.USER_LOGOUT: "Wylogowano się",
    AuditEvent.EMAIL_VERIFIED: "Potwierdzono adres email",
    AuditEvent.PASSWORD_CHANGED: "Zmieniono hasło",
    AuditEvent.PASSWORD_CHANGE_REQUESTED: "Zażądano zmiany hasła",
    AuditEvent.EMAIL_CHANGE_REQUESTED: "Zażądano zmiany adresu email",
    AuditEvent.EMAIL_CHANGED: "Zmieniono adres email",
    AuditEvent.PROFILE_UPDATED: "Zaktualizowano dane profilu",
    AuditEvent.CLIENT_CREATED: "Dodano klienta",
    AuditEvent.CLIENT_UPDATED: "Zaktualizowano klienta",
    AuditEvent.CLIENT_DELETED: "Usunięto klienta",
    AuditEvent.REQUEST_CREATED: "Utworzono prośbę",
    AuditEvent.REQUEST_UPDATED: "Zaktualizowano prośbę",
    AuditEvent.REQUEST_CLOSED: "Zamknięto prośbę",
    AuditEvent.REQUEST_REOPENED: "Otwarto ponownie prośbę",
    AuditEvent.INVITATION_SENT: "Wysłano zaproszenie z linkiem",
    AuditEvent.DOCUMENT_UPLOADED: "Klient przesłał dokument",
    AuditEvent.DOCUMENT_ACCEPTED: "Dokument zaakceptowany",
    AuditEvent.DOCUMENT_REJECTED: "Dokument odrzucony",
    AuditEvent.REMINDER_SENT: "Wysłano przypomnienie",
    AuditEvent.PUBLIC_LINK_ACCESSED: "Klient otworzył link",
    AuditEvent.PASSWORD_ACCESS_FAILED: "Nieudana próba dostępu (błędne hasło)",
    AuditEvent.FILE_DOWNLOAD: "Pobrano dokument",
    AuditEvent.FILE_DELETED: "Usunięto przesłany dokument",
    AuditEvent.DOCUMENTS_ANONYMIZED: "Usunięto pliki po okresie przechowywania",
    AuditEvent.ACCOUNT_DELETION_REQUESTED: "Zażądano usunięcia konta",
}


def translate_event(event_code):
    return EVENT_LABELS_PL.get(event_code, event_code)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditService:
    @staticmethod
    def log(event, actor=None, target=None, request=None, metadata=None):
        content_type = None
        object_id = None
        if target is not None:
            content_type = ContentType.objects.get_for_model(target)
            object_id = target.pk

        request_id = ""
        ip_address = None
        user_agent = ""
        if request is not None:
            request_id = getattr(request, "request_id", "")
            ip_address = _client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

        return AuditLog.objects.create(
            actor=actor,
            event=event,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
            content_type=content_type,
            object_id=object_id,
        )

    @staticmethod
    def history_for_request(request_obj):
        from apps.documents.models import Document
        from apps.requests.models import Request, RequestItem

        item_ids = list(request_obj.items.values_list("pk", flat=True))
        document_ids = list(
            Document.objects.filter(request_item__request=request_obj).values_list(
                "pk", flat=True
            )
        )

        return AuditLog.objects.filter(
            Q(
                content_type=ContentType.objects.get_for_model(Request),
                object_id=request_obj.pk,
            )
            | Q(
                content_type=ContentType.objects.get_for_model(RequestItem),
                object_id__in=item_ids,
            )
            | Q(
                content_type=ContentType.objects.get_for_model(Document),
                object_id__in=document_ids,
            )
        ).order_by("-created_at")
