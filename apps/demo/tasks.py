from celery import shared_task

from apps.demo.services import DemoService


@shared_task
def delete_expired_demo_accounts():
    return DemoService.delete_expired()
