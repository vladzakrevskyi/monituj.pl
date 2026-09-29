"""Tells every account about new versions of the legal documents.

    python manage.py notify_legal_update --changes "Co się zmienia, krótko."

Run it after publishing new wording with a new date in .env (LEGAL_*_DATE) - for
the Regulamin and the umowa powierzenia at least 14 days ahead, so people
can read the new wording (it is on the site already) and delete the account
before it applies. Each person is told only about the documents whose
current version they haven't accepted; from each date the panel asks them
to accept.

Safe to run again: nobody is emailed twice about the same versions.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.common import legal
from apps.common.site import absolute_url
from apps.consents.models import LegalAcceptance, LegalUpdateNotice
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

NOTICE_DAYS = 14


def _announced():
    """The versions this run announces - the key that stops a second email."""
    return "|".join(f"{key}:{legal.version(key)}" for key in legal.ACCEPTED)


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
        announced = _announced()
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

        accepted = {}
        for user_id, document, version in LegalAcceptance.objects.values_list(
            "user_id", "document", "version"
        ):
            accepted.setdefault(user_id, set()).add((document, version))
        already_told = LegalUpdateNotice.objects.filter(version=announced).values(
            "user_id"
        )
        users = (
            User.objects.filter(is_active=True, email_verified_at__isnull=False)
            .exclude(demo_account__isnull=False)
            .exclude(pk__in=already_told)
            .order_by("pk")
        )
        recipients = []
        for user in users.iterator():
            new = [
                key
                for key in legal.ACCEPTED
                if (key, legal.version(key)) not in accepted.get(user.pk, set())
            ]
            if new:
                recipients.append((user, new))
        if dry_run:
            self.stdout.write(f"Would email {len(recipients)} accounts.")
            return

        sent = 0
        for user, new in recipients:
            try:
                LegalUpdateNotice.objects.create(user=user, version=announced)
            except IntegrityError:
                continue  # another run got there first
            EmailService.send(
                EmailTemplate.LEGAL_UPDATE,
                to_email=user.email,
                context={
                    "changes": changes,
                    "documents": [
                        {
                            "title": legal.DOCUMENTS[key].title,
                            "url": absolute_url(reverse(legal.DOCUMENTS[key].url_name)),
                            "since": legal.effective_date_display(key),
                        }
                        for key in new
                    ],
                    "effective_date": legal.effective_date_display(
                        max(new, key=legal.effective_date)
                    ),
                    "settings_url": absolute_url(reverse("accounts:settings")),
                },
            )
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Emailed {sent} accounts."))
