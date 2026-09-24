from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ThrottleEvent(models.Model):
    """One row per counted action (a failed login, a sent email...), keyed by
    what is being limited, e.g. "login-ip:<hash>". See apps.common.throttle."""

    key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["key", "created_at"])]

    def __str__(self):
        return self.key
