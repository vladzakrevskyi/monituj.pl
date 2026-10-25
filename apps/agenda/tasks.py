from celery import shared_task


@shared_task
def send_daily_agenda():
    """ "Na dziś" to everyone whose 7:30 on a working day has come."""
    from apps.agenda import digest

    return digest.send_due()
