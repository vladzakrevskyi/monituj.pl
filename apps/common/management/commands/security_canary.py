"""Plants the canary: an account and a client with an address that exists
only in this database (SECURITY_CANARY_EMAIL in .env). Nobody is ever sent
anything there by Monituj - the account is inactive and unverified, with no
password. So:

- a message arriving at that address means someone has the users or clients
  table and is mailing everyone in it;
- a sign-in or password reset tried with it raises an alarm at once
  (apps/common/security_watch.py).

Use an address only you receive, e.g. an alias of your mailbox with a random
part. Safe to run again; `--remove` takes the canary out."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.clients.models import Client

NAME = "Archiwum Rozliczeń"


class Command(BaseCommand):
    help = "Plants (or removes) the canary account and client."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **options):
        email = settings.SECURITY_CANARY_EMAIL
        if not email:
            raise CommandError("Ustaw SECURITY_CANARY_EMAIL w .env.")
        existing = User.objects.filter(email__iexact=email).first()
        if options["remove"]:
            if existing is not None and not existing.is_active:
                Client.objects.filter(owner=existing).delete()
                existing.delete()
            self.stdout.write("Przynęta usunięta.")
            return
        if existing is not None and (
            existing.is_active or existing.has_usable_password()
        ):
            raise CommandError(
                f"{email} to prawdziwe konto - przynęta musi mieć adres, którego "
                "nikt nie używa."
            )
        user = existing or User(email=email)
        user.display_name = NAME
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.email_verified_at = None
        user.set_unusable_password()
        user.save()
        Client.objects.get_or_create(owner=user, email=email, defaults={"name": NAME})
        self.stdout.write(
            f"Przynęta gotowa: konto i klient z adresem {email}. Wiadomość na ten "
            "adres albo próba logowania nim = ktoś czytał bazę."
        )
