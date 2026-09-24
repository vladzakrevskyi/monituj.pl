"""Evidence of what people agreed to - kept so it can be shown later
(art. 7(1) RODO for consents; the accepted version of the Terms for the
contract). Rows are only ever added, never changed."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class LegalDocument(models.TextChoices):
    TERMS = "regulamin", "Regulamin"
    DPA = "umowa_powierzenia", "Umowa powierzenia przetwarzania danych"
    PRIVACY = "polityka_prywatnosci", "Polityka prywatności"


class AcceptanceMethod(models.TextChoices):
    REGISTRATION = "rejestracja", "Rejestracja (email i hasło)"
    GOOGLE = "google", "Rejestracja przez Google"
    GUEST_REQUEST = "prosba_bez_konta", "Prośba bez konta"
    UPDATE = "aktualizacja", "Akceptacja nowej wersji"


class LegalAcceptance(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legal_acceptances",
    )
    document = models.CharField(max_length=32, choices=LegalDocument.choices)
    # The documents' effective date (LEGAL_EFFECTIVE_DATE) at the moment of
    # acceptance - which wording the person agreed to.
    version = models.CharField(max_length=64)
    method = models.CharField(max_length=32, choices=AcceptanceMethod.choices)
    accepted_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-accepted_at", "-id"]
        indexes = [models.Index(fields=["user", "document", "version"])]

    def __str__(self):
        return f"{self.document} {self.version} by {self.user_id}"


class LegalUpdateNotice(models.Model):
    """Who has been emailed about a new version - so the command can be run
    again (after a failure, for new users) without mailing anyone twice."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legal_update_notices",
    )
    version = models.CharField(max_length=64)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "version"], name="one_legal_notice_per_version"
            )
        ]


class CookieConsent(models.Model):
    """A cookie banner decision. Anonymous: a random id kept in the
    visitor's browser, no IP address, no account."""

    consent_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    version = models.CharField(max_length=32)
    choices = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.consent_id} {self.choices}"
