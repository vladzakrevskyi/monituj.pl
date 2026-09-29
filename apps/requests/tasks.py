from celery import shared_task

from apps.requests.guest import GuestRequestService
from apps.requests.services import RequestService


@shared_task
def delete_unconfirmed_requests():
    return GuestRequestService.delete_unconfirmed()


@shared_task
def send_queued_invitations():
    return RequestService.send_queued_invitations()


@shared_task
def send_recurring_requests():
    from apps.requests.recurring import run_due

    return run_due()
