"""Fills an account with random requests for testing - lists, filters, the
dashboard, plan limits.

    python manage.py generate_requests --email jan@firma.pl --count 15

Recipients get made-up addresses in the reserved example.com domain, which
belongs to no one. Nothing is emailed: requests are stored directly, without
the invitation, and plan limits are not checked. Automatic reminders stay off
unless --reminders is given (they would otherwise be mailed to those
addresses). Refuses to run with DEBUG=False unless --force."""

import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.clients.models import Client
from apps.common.content import SEGMENTS
from apps.requests.models import Request, RequestItem

FIRST_NAMES = [
    "Anna", "Piotr", "Katarzyna", "Tomasz", "Magdalena", "Marcin", "Agnieszka",
    "Paweł", "Joanna", "Michał", "Ewa", "Krzysztof", "Monika", "Łukasz", "Zofia",
]  # fmt: skip
LAST_NAMES = [
    "Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kamiński", "Lewandowski",
    "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", "Mazur",
]  # fmt: skip
COMPANIES = [
    "Budmax", "Transpol", "Zielony Ogród", "Pixel Studio", "Agromet", "Fotoplus",
    "Mebloteka", "Autoserwis Kowal", "Kwiaciarnia Róża", "Dom Zdrowia",
]  # fmt: skip
COMPANY_FORMS = ["Sp. z o.o.", "s.c.", "S.A.", ""]
MONTHS = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec",
    "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]  # fmt: skip
REQUEST_NAMES = [
    "Dokumenty za {month} {year}",
    "Rozliczenie za {month} {year}",
    "Akta nowego pracownika",
    "Dokumenty do sprawy",
    "Dokumenty do wniosku kredytowego",
    "Komplet dokumentów do umowy",
    "Zamknięcie roku {year}",
]
ASCII = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
DOCUMENT_NAMES = sorted({name for segment in SEGMENTS for name in segment["examples"]})


def _person(rng):
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    if last.endswith("ski") and first.endswith("a"):
        last = last[:-1] + "a"
    return first, last


def _recipient(rng):
    """(name, address) - a person or a company, always at example.com."""
    number = rng.randint(100, 9999)
    if rng.random() < 0.5:
        first, last = _person(rng)
        local = f"{first}.{last}".lower().translate(ASCII)
        return f"{first} {last}", f"{local}.{number}@example.com"
    company = rng.choice(COMPANIES)
    name = f"{company} {rng.choice(COMPANY_FORMS)}".strip()
    local = "".join(ch for ch in company.lower().translate(ASCII) if ch.isalnum())
    return name, f"biuro.{local}.{number}@example.com"


class Command(BaseCommand):
    help = "Creates random requests (to example.com addresses) in an account."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Account to fill.")
        parser.add_argument("--count", type=int, required=True, help="How many.")
        parser.add_argument(
            "--reminders",
            action="store_true",
            help="Turn automatic reminders on (they will be mailed to the "
            "made-up example.com addresses).",
        )
        parser.add_argument("--seed", type=int, help="Same seed, same data.")
        parser.add_argument(
            "--force", action="store_true", help="Run even with DEBUG=False."
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False - is this production? Add --force if you are sure."
            )
        count = options["count"]
        if not 1 <= count <= 500:
            raise CommandError("--count must be between 1 and 500.")
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError(f"No account with the address {options['email']}.")

        rng = random.Random(options["seed"])
        now = timezone.now()
        with transaction.atomic():
            for _ in range(count):
                request_obj = self._create(user, rng, now, options["reminders"])
                self.stdout.write(
                    f"  {request_obj.name} → {request_obj.client.email} "
                    f"({request_obj.items.count()} dok.)"
                )
        self.stdout.write(
            self.style.SUCCESS(f"Utworzono {count} próśb dla {user.email}.")
        )

    def _create(self, user, rng, now, reminders):
        name, email = _recipient(rng)
        client, _ = Client.objects.get_or_create(
            owner=user, email=email, defaults={"name": name}
        )
        month = now - timedelta(days=rng.randint(0, 90))
        title = rng.choice(REQUEST_NAMES).format(
            month=MONTHS[month.month - 1], year=month.year
        )
        # Mostly upcoming deadlines, some already missed, some without one.
        deadline = None
        if rng.random() < 0.85:
            deadline = (now + timedelta(days=rng.randint(-7, 30))).replace(
                hour=23, minute=59, second=0, microsecond=0
            )
        request_obj = Request.objects.create(
            client=client,
            created_by=user,
            name=title,
            deadline=deadline,
            reminders_enabled=reminders,
            sender_timezone=user.timezone,
            retention_days=rng.choice([30, 90, 180, 365]),
        )
        RequestItem.objects.bulk_create(
            RequestItem(request=request_obj, name=document)
            for document in rng.sample(DOCUMENT_NAMES, rng.randint(2, 6))
        )
        AuditService.log(
            AuditEvent.REQUEST_CREATED,
            actor=user,
            target=request_obj,
            metadata={"generated": True},
        )
        return request_obj
