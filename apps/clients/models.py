from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel


class Client(TimeStampedModel):
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="clients")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self):
        return self.name
