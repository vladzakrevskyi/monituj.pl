from celery import shared_task
from django.utils import timezone

from apps.clients.models import ClientImport
from apps.common.throttle import DAY


@shared_task
def delete_old_client_imports():
    """A file uploaded for import and never imported holds client data -
    it goes after a day."""
    deleted, _ = ClientImport.objects.filter(
        created_at__lt=timezone.now() - DAY
    ).delete()
    return deleted
