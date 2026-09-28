import os
import sys

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("monituj")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# On macOS the prefork pool starts its children with "spawn", and Celery's
# task runner isn't set up in them ("not enough values to unpack (expected 3,
# got 0)"). Locally one process is plenty; servers (Linux) fork as usual.
if sys.platform == "darwin":
    app.conf.worker_pool = "solo"
