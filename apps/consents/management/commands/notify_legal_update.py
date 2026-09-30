"""Tells every account about new versions of the legal documents.

    python manage.py notify_legal_update --changes "Co się zmienia, krótko."

Run it after publishing new wording with a new date in .env (LEGAL_*_DATE) - for
the Regulamin and the umowa powierzenia at least 14 days ahead, so people
can read the new wording (it is on the site already) and delete the account
before it applies. Each person is told only about the documents whose
current version they haven't accepted; from each date the panel asks them
to accept.

Safe to run again: nobody is emailed twice about the same versions. The
announcement is kept, and whoever joins during the notice period gets the
same email within an hour (apps/consents/announcements.py).
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common import legal
from apps.consents import announcements

NOTICE_DAYS = 14


class Command(BaseCommand):
    help = "Emails every account about new versions of the legal documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--changes",
            required=True,
            help="A short summary of what changes, shown in the email.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only count who would get the email.",
        )

    def handle(self, *args, changes, dry_run, **options):
        soon = timezone.localdate() + timedelta(days=NOTICE_DAYS)
        for key in (legal.TERMS, legal.DPA):
            if legal.effective_date(key) < soon:
                self.stdout.write(
                    self.style.WARNING(
                        f"{legal.DOCUMENTS[key].title} applies from "
                        f"{legal.version(key)} - less than {NOTICE_DAYS} days "
                        "from now. If it changed, the Regulamin promises "
                        f"{NOTICE_DAYS} days' notice."
                    )
                )
        if dry_run:
            count = len(announcements.recipients())
            self.stdout.write(f"Would email {count} accounts.")
            return
        announcements.publish(changes)
        sent = announcements.send()
        self.stdout.write(self.style.SUCCESS(f"Emailed {sent} accounts."))
