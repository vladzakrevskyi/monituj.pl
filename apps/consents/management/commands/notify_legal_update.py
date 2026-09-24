"""Tells every account about new Terms / Privacy policy / DPA.

    python manage.py notify_legal_update --changes "Co się zmienia, krótko."

Run it after publishing the new documents with a new LEGAL_EFFECTIVE_DATE -
best a date at least 14 days ahead, so people can read the new wording (it
is on the site already) and delete the account before it applies. From that
date the panel asks each user to accept the new version.

Safe to run again: nobody is emailed twice about the same version.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.models import User
from apps.common import legal
from apps.common.site import absolute_url
from apps.consents.models import LegalAcceptance, LegalDocument, LegalUpdateNotice
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService


class Command(BaseCommand):
    help = "Emails every account about a new version of the legal documents."

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
        version = legal.version()
        if not version:
            raise CommandError("Set LEGAL_EFFECTIVE_DATE to the new version first.")
        if legal.effective_date() is None:
            raise CommandError(
                "LEGAL_EFFECTIVE_DATE must be a date (2026-10-01 or 01.10.2026)."
            )

        already_accepted = LegalAcceptance.objects.filter(
            document=LegalDocument.TERMS, version=version
        ).values("user_id")
        already_told = LegalUpdateNotice.objects.filter(version=version).values(
            "user_id"
        )
        users = (
            User.objects.filter(is_active=True, email_verified_at__isnull=False)
            .exclude(demo_account__isnull=False)
            .exclude(pk__in=already_accepted)
            .exclude(pk__in=already_told)
            .order_by("pk")
        )
        if dry_run:
            self.stdout.write(f"Would email {users.count()} accounts about {version}.")
            return

        context = {
            "changes": changes,
            "effective_date": legal.effective_date_display(),
            "terms_url": absolute_url(reverse("legal:terms")),
            "privacy_url": absolute_url(reverse("legal:privacy")),
            "dpa_url": absolute_url(reverse("legal:dpa")),
            "settings_url": absolute_url(reverse("accounts:settings")),
        }
        sent = 0
        for user in users.iterator():
            try:
                LegalUpdateNotice.objects.create(user=user, version=version)
            except IntegrityError:
                continue  # another run got there first
            EmailService.send(
                EmailTemplate.LEGAL_UPDATE, to_email=user.email, context=context
            )
            sent += 1
        self.stdout.write(
            self.style.SUCCESS(f"Emailed {sent} accounts about {version}.")
        )
