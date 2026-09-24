from celery import shared_task

from apps.notifications.inbox import send_pending_upload_emails


@shared_task
def send_upload_emails():
    return send_pending_upload_emails()
