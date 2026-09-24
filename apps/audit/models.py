from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.accounts.models import User


class AuditEvent(models.TextChoices):
    USER_REGISTERED = "USER_REGISTERED", "User registered"
    USER_LOGIN = "USER_LOGIN", "User login"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED", "User login failed"
    USER_LOGOUT = "USER_LOGOUT", "User logout"
    EMAIL_VERIFIED = "EMAIL_VERIFIED", "Email verified"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
    PASSWORD_CHANGE_REQUESTED = "PASSWORD_CHANGE_REQUESTED", "Password change requested"
    EMAIL_CHANGE_REQUESTED = "EMAIL_CHANGE_REQUESTED", "Email change requested"
    EMAIL_CHANGED = "EMAIL_CHANGED", "Email changed"
    PROFILE_UPDATED = "PROFILE_UPDATED", "Profile updated"
    CLIENT_CREATED = "CLIENT_CREATED", "Client created"
    CLIENT_UPDATED = "CLIENT_UPDATED", "Client updated"
    CLIENT_DELETED = "CLIENT_DELETED", "Client deleted"
    REQUEST_CREATED = "REQUEST_CREATED", "Request created"
    REQUEST_UPDATED = "REQUEST_UPDATED", "Request updated"
    INVITATION_SENT = "INVITATION_SENT", "Invitation sent"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED", "Document uploaded"
    DOCUMENT_ACCEPTED = "DOCUMENT_ACCEPTED", "Document accepted"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED", "Document rejected"
    REMINDER_SENT = "REMINDER_SENT", "Reminder sent"
    PUBLIC_LINK_ACCESSED = "PUBLIC_LINK_ACCESSED", "Public link accessed"
    PASSWORD_ACCESS_FAILED = "PASSWORD_ACCESS_FAILED", "Password access failed"
    FILE_DOWNLOAD = "FILE_DOWNLOAD", "File download"
    FILE_DELETED = "FILE_DELETED", "File deleted"
    DOCUMENTS_ANONYMIZED = "DOCUMENTS_ANONYMIZED", "Documents anonymized"
    ACCOUNT_DELETION_REQUESTED = (
        "ACCOUNT_DELETION_REQUESTED",
        "Account deletion requested",
    )


class AuditLog(models.Model):
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    event = models.CharField(max_length=64, choices=AuditEvent.choices)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event} at {self.created_at}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLog entries are append-only and cannot be modified.")
        super().save(*args, **kwargs)
