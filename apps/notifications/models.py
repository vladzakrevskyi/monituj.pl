from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.requests.models import Request


class EmailTemplate(models.TextChoices):
    INVITATION = "zaproszenie", "Zaproszenie"
    REMINDER = "przypomnienie", "Przypomnienie"
    UPLOAD_CONFIRMATION = "potwierdzenie_uploadu", "Potwierdzenie uploadu"
    COMPLETE = "komplet_dokumentow", "Komplet dokumentów"
    REJECTION = "odrzucenie", "Odrzucenie"
    EMAIL_VERIFICATION = "weryfikacja_email", "Weryfikacja email"
    PASSWORD_RESET = "reset_hasla", "Reset hasła"
    ACCESS_PASSWORD = "haslo_dostepu", "Hasło dostępu"
    PASSWORD_CHANGE_CONFIRM = "potwierdzenie_zmiany_hasla", "Potwierdzenie zmiany hasła"
    PASSWORD_CHANGED_NOTICE = "haslo_zmienione", "Hasło zmienione"
    EMAIL_CHANGE_CONFIRM = "potwierdzenie_zmiany_email", "Potwierdzenie zmiany email"
    EMAIL_CHANGE_REQUESTED_NOTICE = "prosba_zmiany_email", "Prośba o zmianę email"
    EMAIL_CHANGED_NOTICE = "email_zmieniony", "Email zmieniony"
    ANONYMIZED_OWNER = "anonimizacja_wlasciciel", "Anonimizacja (właściciel)"
    ANONYMIZED_CLIENT = "anonimizacja_odbiorca", "Anonimizacja (odbiorca)"
    ACCOUNT_DELETION_CONFIRM = (
        "potwierdzenie_usuniecia_konta",
        "Potwierdzenie usunięcia konta",
    )
    ACCOUNT_DELETED = "konto_usuniete", "Konto usunięte"
    REQUEST_CANCELLED = "prosba_anulowana", "Prośba anulowana"
    GUEST_REQUEST_CONFIRM = "potwierdzenie_prosby", "Potwierdzenie prośby bez konta"
    GUEST_PANEL_ACCESS = "dostep_do_panelu", "Dostęp do panelu bez hasła"
    COMPLETE_OWNER = "komplet_wlasciciel", "Komplet dokumentów (nadawca)"
    CONTACT_MESSAGE = "kontakt_wiadomosc", "Formularz kontaktowy"
    CONTACT_CONFIRMATION = (
        "kontakt_potwierdzenie",
        "Formularz kontaktowy (potwierdzenie)",
    )
    UPLOAD_OWNER = "dokument_dodany", "Nowy dokument (nadawca)"
    GOOGLE_LINKED = "google_polaczone", "Logowanie Google dodane"
    GOOGLE_UNLINKED = "google_odlaczone", "Logowanie Google odłączone"
    GOOGLE_LINK_CONFIRM = "google_potwierdz", "Potwierdzenie połączenia z Google"


class EmailStatus(models.TextChoices):
    SENT = "sent", "Wysłany"
    FAILED = "failed", "Błąd"
    SKIPPED = "skipped", "Pominięty (demo)"


class EmailLog(TimeStampedModel):
    recipient_email = models.EmailField()
    template = models.CharField(max_length=32, choices=EmailTemplate.choices)
    request = models.ForeignKey(
        Request,
        on_delete=models.SET_NULL,
        related_name="email_logs",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=EmailStatus.choices)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["recipient_email", "template"])]

    def __str__(self):
        return f"{self.template} to {self.recipient_email}"


class NotificationKind(models.TextChoices):
    DOCUMENT_UPLOADED = "dokument_dodany", "Dodano dokument"


class Notification(TimeStampedModel):
    """What a sender sees under "Powiadomienia" in the panel - and what the
    upload email is built from. Points at the document instead of copying its
    name, so deleting or anonymizing the file takes the trace with it."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(
        max_length=32,
        choices=NotificationKind.choices,
        default=NotificationKind.DOCUMENT_UPLOADED,
    )
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["emailed_at"]),
        ]

    def __str__(self):
        return f"{self.kind} for {self.user_id}"
