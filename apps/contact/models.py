from django.db import models


class ContactThrottle(models.Model):
    """One row per sent contact message, keyed by a hash of the sender's IP.
    Only used to limit how often the form can be sent - the message itself
    is not stored, it goes straight to the mailbox."""

    ip_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.ip_hash[:8]} at {self.created_at}"
