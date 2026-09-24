from celery import shared_task

from apps.reminders.services import AutomaticReminderService
from apps.requests.models import Request


@shared_task
def send_automatic_reminders():
    request_ids = list(
        Request.objects.filter(reminders_enabled=True).values_list("pk", flat=True)
    )
    sent_count = 0
    for request_id in request_ids:
        if AutomaticReminderService.maybe_send_for_request(request_id):
            sent_count += 1
    return sent_count
