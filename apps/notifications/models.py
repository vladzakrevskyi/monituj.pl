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
    CONTACT_MESSAGE = "kontakt_wiadomosc", "Formularz kontaktowy"
    CONTACT_CONFIRMATION = (
        "kontakt_potwierdzenie",
        "Formularz kontaktowy (potwierdzenie)",
    )


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
