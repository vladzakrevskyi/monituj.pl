"""Sends a security alarm from outside the site - the server's own checks
(deploy/security/: an SSH login, a changed system file) call it:

    echo "details" | docker compose exec -T web python manage.py \\
        security_alert "logowanie SSH: deploy z 1.2.3.4"

The details come on standard input. `--key` names the alarm for the "once
per 10 minutes" rule (default: the subject)."""

import sys

from django.core.management.base import BaseCommand

from apps.common import security_watch


class Command(BaseCommand):
    help = "Sends a security alarm (details on standard input)."

    def add_arguments(self, parser):
        parser.add_argument("subject")
        parser.add_argument("--key", default=None)

    def handle(self, *args, **options):
        details = "" if sys.stdin.isatty() else sys.stdin.read()
        lines = [line.rstrip() for line in details.strip().splitlines()][:200]
        sent = security_watch.alert(
            options["subject"][:150], ["Źródło: serwer", *lines], key=options["key"]
        )
        self.stdout.write("wysłano" if sent else "pominięto (wyłączone albo powtórka)")
