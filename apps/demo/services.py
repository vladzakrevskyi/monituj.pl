import hashlib
import secrets
from datetime import datetime, time, timedelta

from django.contrib.auth import login
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.accounts.erasure import erase_account
from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditLog
from apps.clients.models import Client
from apps.common.exceptions import RateLimitedAppError
from apps.common.security import get_client_ip, hash_ip
from apps.demo.models import DEMO_EMAIL_DOMAIN, DemoAccount
from apps.documents.models import Document, DocumentStatus
from apps.documents.storage import save_document_file
from apps.reminders.models import Reminder, ReminderKind
from apps.requests.models import Request, RequestItem
from apps.requests.models import RequestItemStatus as Status

DEMO_LIFETIME = timedelta(hours=24)
DEMO_MAX_PER_IP = 10
LIMIT_MESSAGE = (
    "Z tego adresu uruchomiono dziś już kilka wersji demo. Załóż bezpłatne konto, "
    "aby dalej korzystać z Monituj."
)


_ASCII = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def _pdf(title):
    """A small but valid one-page PDF, so demo downloads open normally. The
    built-in Helvetica font only covers Latin-1, hence the transliteration."""
    safe = title.translate(_ASCII)
    safe = safe.replace("\\", "").replace("(", "").replace(")", "")
    stream = (
        f"BT /F1 20 Tf 72 760 Td ({safe}) Tj ET "
        "BT /F1 11 Tf 72 730 Td (Plik demonstracyjny Monituj) Tj ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return out


class _Seeder:
    """Builds a realistic account: clients, requests in every state, uploaded
    files, sent reminders and an event history, all dated in the past."""

    def __init__(self, user, now):
        self.user = user
        self.now = now
        self.types = {
            model: ContentType.objects.get_for_model(model)
            for model in (Request, RequestItem, Document)
        }

    def at(self, days_ago, hour=10, minute=0):
        day = timezone.localtime(self.now).date() - timedelta(days=days_ago)
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def end_of_day(self, days_from_now):
        day = timezone.localtime(self.now).date() + timedelta(days=days_from_now)
        return timezone.make_aware(datetime.combine(day, time.max))

    def client(self, name, email, phone=""):
        return Client.objects.create(
            owner=self.user, name=name, email=email, phone=phone
        )

    def request(self, client, name, created, deadline, description="", **settings):
        request_obj = Request.objects.create(
            client=client,
            created_by=self.user,
            name=name,
            description=description,
            deadline=deadline,
            **settings,
        )
        Request.objects.filter(pk=request_obj.pk).update(created_at=created)
        self.log(AuditEvent.REQUEST_CREATED, request_obj, created, actor=self.user)
        self.log(AuditEvent.INVITATION_SENT, request_obj, created, actor=self.user)
        return request_obj

    def item(self, request_obj, name, status, uploaded=None, reason=""):
        item = RequestItem.objects.create(
            request=request_obj, name=name, status=status, rejection_reason=reason
        )
        if uploaded is not None:
            document_status = {
                Status.ZAAKCEPTOWANY: DocumentStatus.ACCEPTED,
                Status.ODRZUCONY: DocumentStatus.REJECTED,
            }.get(status, DocumentStatus.UPLOADED)
            content = _pdf(name)
            key = f"demo/{secrets.token_hex(16)}.pdf"
            encryption_fields = save_document_file(key, content)
            document = Document.objects.create(
                request_item=item,
                storage_key=key,
                original_filename=f"{name.lower().replace(' ', '_')}.pdf",
                content_type="application/pdf",
                size=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                status=document_status,
                **encryption_fields,
            )
            Document.objects.filter(pk=document.pk).update(uploaded_at=uploaded)
            self.log(AuditEvent.DOCUMENT_UPLOADED, document, uploaded)
            reviewed = uploaded + timedelta(hours=2)
            if status == Status.ZAAKCEPTOWANY:
                self.log(AuditEvent.DOCUMENT_ACCEPTED, item, reviewed, actor=self.user)
            elif status == Status.ODRZUCONY:
                self.log(AuditEvent.DOCUMENT_REJECTED, item, reviewed, actor=self.user)
        return item

    def opened(self, request_obj, when):
        self.log(AuditEvent.PUBLIC_LINK_ACCESSED, request_obj, when)

    def reminder(self, request_obj, when, number):
        reminder = Reminder.objects.create(
            request=request_obj, kind=ReminderKind.AUTOMATIC, sequence_number=number
        )
        Reminder.objects.filter(pk=reminder.pk).update(sent_at=when)
        self.log(AuditEvent.REMINDER_SENT, request_obj, when)

    def log(self, event, target, when, actor=None):
        entry = AuditLog.objects.create(
            event=event,
            actor=actor,
            content_type=self.types[type(target)],
            object_id=target.pk,
        )
        AuditLog.objects.filter(pk=entry.pk).update(created_at=when)

    def seed(self):
        kowalski = self.client(
            "Kowalski Sp. z o.o.", "biuro@kowalski.example.com", "+48 600 100 200"
        )
        nowak = self.client("Anna Nowak", "anna.nowak@example.com")
        wisniewski = self.client("Jan Wiśniewski", "jan.wisniewski@example.com")
        kowalczyk = self.client(
            "Firma Budowlana Kowalczyk", "kontakt@kowalczyk.example.com"
        )
        self.client("Studio Graficzne Pixel", "hello@pixel.example.com")

        september = self.request(
            kowalski,
            "Dokumenty za wrzesień",
            created=self.at(3, 9, 15),
            deadline=self.end_of_day(4),
            description="Dokumenty potrzebne do zamknięcia miesiąca.",
            retention_days=90,
        )
        self.opened(september, self.at(2, 11, 40))
        self.item(
            september,
            "Faktury sprzedaży",
            Status.ZAAKCEPTOWANY,
            uploaded=self.at(2, 11, 52),
        )
        self.item(
            september, "Faktury kosztowe", Status.DOSTARCZONY, uploaded=self.at(1, 16)
        )
        self.item(september, "Wyciąg bankowy", Status.BRAK)
        self.item(september, "Raport kasowy", Status.BRAK)
        self.reminder(september, self.at(1, 9), 1)

        onboarding = self.request(
            nowak,
            "Akta nowego pracownika",
            created=self.at(10, 8, 30),
            deadline=self.end_of_day(-2),
            retention_days=180,
        )
        self.opened(onboarding, self.at(9, 19, 5))
        for offset, name in enumerate(
            [
                "Świadectwo pracy",
                "Orzeczenie lekarskie",
                "Kwestionariusz osobowy",
                "Dyplom",
            ]
        ):
            self.item(
                onboarding,
                name,
                Status.ZAAKCEPTOWANY,
                uploaded=self.at(9, 19, 10 + offset * 3),
            )

        loan = self.request(
            wisniewski,
            "Wniosek kredytowy",
            created=self.at(8, 14),
            deadline=self.end_of_day(-1),
            retention_days=30,
        )
        for name in ["Zaświadczenie o dochodach", "Wyciąg z konta", "Umowa o pracę"]:
            self.item(loan, name, Status.BRAK)
        self.reminder(loan, self.at(6, 9), 1)
        self.reminder(loan, self.at(3, 9), 2)

        year_end = self.request(
            kowalczyk,
            "Zamknięcie roku 2025",
            created=self.at(5, 12),
            deadline=self.end_of_day(10),
            retention_days=365,
        )
        self.opened(year_end, self.at(4, 17, 20))
        self.item(
            year_end,
            "Bilans",
            Status.ODRZUCONY,
            uploaded=self.at(4, 17, 30),
            reason="Brakuje podpisu na ostatniej stronie.",
        )
        self.item(
            year_end,
            "Rachunek zysków i strat",
            Status.DOSTARCZONY,
            uploaded=self.at(4, 17, 34),
        )
        self.item(year_end, "Protokół inwentaryzacji", Status.BRAK)
        return september


class DemoService:
    @staticmethod
    def start(django_request):
        """Creates a fresh demo account for this visitor and logs them in."""
        now = timezone.now()
        ip_hash = hash_ip(get_client_ip(django_request))
        recent = DemoAccount.objects.filter(
            ip_hash=ip_hash, created_at__gte=now - timedelta(hours=24)
        ).count()
        if recent >= DEMO_MAX_PER_IP:
            raise RateLimitedAppError(LIMIT_MESSAGE, code="DEMO_LIMIT_REACHED")

        with transaction.atomic():
            user = User.objects.create_user(
                email=f"demo-{secrets.token_hex(8)}@{DEMO_EMAIL_DOMAIN}",
                display_name="Biuro Rachunkowe Demo",
                email_verified_at=now,
            )
            DemoAccount.objects.create(
                user=user, ip_hash=ip_hash, expires_at=now + DEMO_LIFETIME
            )
            _Seeder(user, now).seed()

        login(django_request, user, backend="django.contrib.auth.backends.ModelBackend")
        django_request.session.set_expiry(user.demo_account.expires_at)
        return user

    @staticmethod
    def showcase_request(user):
        """The request shown in the "see it as your client" shortcut."""
        return (
            Request.objects.filter(created_by=user, items__status=Status.BRAK)
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def delete(user):
        erase_account(user)

    @staticmethod
    def delete_expired(now=None):
        now = now or timezone.now()
        expired = User.objects.filter(demo_account__expires_at__lte=now)
        count = 0
        for user in expired:
            DemoService.delete(user)
            count += 1
        return count
