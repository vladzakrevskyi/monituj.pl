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


class LegalVersion(models.Model):
    """One wording of a legal document, exactly as it was shown (the HTML of
    its page, operator details filled in) - so what someone accepted or
    bought on can be shown word for word, years later. Added automatically
    (consents.versions), never changed or deleted. `version` is the date the
    wording applies from; the same date with a different text is a new row
    (and an alert: the text changed without a new version)."""

    document = models.CharField(max_length=32, db_index=True)
    version = models.CharField(max_length=10)
    sha256 = models.CharField(max_length=64)
    html = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["document", "-created_at"]
        verbose_name = "wersja dokumentu"
        verbose_name_plural = "wersje dokumentów"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "sha256"], name="one_row_per_wording"
            )
        ]

    def __str__(self):
        return f"{self.document} {self.version} ({self.sha256[:12]})"


class LegalAcceptance(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legal_acceptances",
    )
    document = models.CharField(max_length=32, choices=LegalDocument.choices)
    # The document's version (the date its wording applies from) and the
    # exact wording, archived.
    version = models.CharField(max_length=64)
    wording = models.ForeignKey(
        LegalVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="acceptances",
    )
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
    # The versions announced, e.g. "regulamin:2026-11-01".
    version = models.CharField(max_length=255)
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


class LegalAnnouncement(models.Model):
    """What notify_legal_update announced about a set of new versions - kept
    so people who join during the notice period get the same email
    (apps/consents/announcements.py)."""

    # The versions announced, e.g. "regulamin:2026-10-15|umowa_powierzenia:…".
    announced = models.CharField(max_length=255, unique=True)
    changes = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.announced
