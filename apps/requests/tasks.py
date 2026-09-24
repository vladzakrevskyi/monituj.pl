from celery import shared_task

from apps.requests.guest import GuestRequestService


@shared_task
def delete_unconfirmed_requests():
    return GuestRequestService.delete_unconfirmed()
