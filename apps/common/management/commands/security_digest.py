"""The daily security report (apps/common/security_digest.py). The server's
cron runs it with its own report on standard input:

    deploy/security/daily-report.sh  ->  manage.py security_digest --host-report -

`--print` shows it instead of sending."""

import sys

from django.core.management.base import BaseCommand

from apps.common import security_digest


class Command(BaseCommand):
    help = "Sends the daily security report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host-report",
            default="",
            help='The server\'s part: a file, or "-" for standard input.',
        )
        parser.add_argument("--print", action="store_true", dest="show")

    def handle(self, *args, **options):
        source = options["host_report"]
        host_report = ""
        if source == "-":
            host_report = sys.stdin.read()
        elif source:
            with open(source, encoding="utf-8", errors="replace") as handle:
                host_report = handle.read()
        if options["show"]:
            subject, body, _ = security_digest.build(host_report=host_report)
            self.stdout.write(f"{subject}\n\n{body}")
            return
        self.stdout.write(security_digest.send(host_report=host_report))
