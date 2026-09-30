"""After every deploy (deploy/deploy.sh runs it): brings the outside world
in line with the new code, then reports what the server runs on.

    python manage.py post_deploy

- Stripe: products, prices, VAT, portal settings and the webhook's events
  (stripe_setup --create-webhook - safe to repeat);
- the legal documents' wording in force, into the archive;
- paid Stripe invoices without a VAT invoice (a webhook lost while the
  site was restarting), queued for inFakt;
- a report: modes of Stripe / inFakt / GUS, maintenance mode, missing
  operator details, stuck invoices and emails.

Never fails the deploy: a problem here is printed as a warning - the site
itself is already up.
"""

import io
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing import gateway, gus, invoicing
from apps.billing.models import BillingNotice, VatInvoice, VatInvoiceStatus
from apps.common import legal
from apps.consents.versions import archive_all


class Command(BaseCommand):
    help = "Syncs Stripe, archives legal documents and reports the setup."

    def handle(self, *args, **options):
        self.warnings = []
        self._step("Stripe", self._stripe)
        self._step("Dokumenty prawne", self._legal)
        self._step("Faktury VAT", self._invoices)
        self._report()
        if self.warnings:
            self.stdout.write(self.style.WARNING("\nDo sprawdzenia:"))
            for warning in self.warnings:
                self.stdout.write(self.style.WARNING(f"  ! {warning}"))
        else:
            self.stdout.write(self.style.SUCCESS("\nWszystko wygląda dobrze."))

    def _step(self, name, action):
        try:
            result = action()
            self.stdout.write(f"  ✓ {name}: {result}")
        except Exception as exc:  # a warning, never a failed deploy
            self.warnings.append(f"{name}: {exc.__class__.__name__}: {exc}")
            self.stdout.write(self.style.ERROR(f"  ✗ {name}: {exc}"))

    # --- sync -------------------------------------------------------------

    def _stripe(self):
        if not gateway.enabled():
            self.warnings.append(
                f"Stripe ({settings.STRIPE_MODE}): brak klucza - płatności wyłączone."
            )
            return "pominięte (brak klucza)"
        out = io.StringIO()
        call_command(
            "stripe_setup",
            create_webhook=settings.SITE_URL.startswith("https://"),
            stdout=out,
        )
        text = out.getvalue()
        if "Wpisz do .env" in text:
            # A webhook was just created: its secret must go into .env.
            line = next(x for x in text.splitlines() if "Wpisz do .env" in x)
            self.warnings.append(
                "Stripe utworzył nowy webhook. "
                + line.strip()
                + " - potem docker compose up -d --force-recreate web worker beat."
            )
        if not gateway.keys().get("webhook_secret"):
            self.warnings.append(
                f"Brak STRIPE_{settings.STRIPE_MODE.upper()}_WEBHOOK_SECRET - "
                "webhooki Stripe są odrzucane."
            )
        return f"zsynchronizowane ({settings.STRIPE_MODE})"

    def _legal(self):
        new = archive_all()
        return f"{new} nowych wersji w archiwum" if new else "bez zmian"

    def _invoices(self):
        if not (gateway.enabled() and invoicing.enabled()):
            return "pominięte (Stripe albo inFakt wyłączony)"
        queued = invoicing.reconcile()
        return f"{queued} brakujących dopisanych do kolejki" if queued else "komplet"

    # --- report -----------------------------------------------------------

    def _report(self):
        warn = self.warnings.append
        self.stdout.write("\nKonfiguracja:")
        self.stdout.write(f"  Strona:      {settings.SITE_URL}")
        self.stdout.write(f"  Stripe:      {settings.STRIPE_MODE}")
        self.stdout.write(
            f"  inFakt:      {invoicing.mode()}"
            + ("" if invoicing.enabled() else " (brak klucza - faktury wyłączone)")
            + (" · KSeF" if settings.INFAKT_SEND_TO_KSEF else "")
        )
        self.stdout.write(f"  GUS:         {settings.GUS_MODE}")
        for key, doc in legal.DOCUMENTS.items():
            state = "obowiązuje" if legal.in_force(key) else "od tego dnia"
            self.stdout.write(
                f"  {doc.title}: {legal.effective_date_display(key)} ({state})"
            )

        if settings.DEBUG:
            warn("DEBUG=True na produkcji.")
        if not settings.SITE_URL.startswith("https://"):
            warn(f"SITE_URL bez https: {settings.SITE_URL}")
        if getattr(settings, "MAINTENANCE_MODE", False):
            warn("MAINTENANCE_MODE=True - odwiedzający widzą „prace techniczne”.")
        if settings.STRIPE_MODE != "live":
            warn("Stripe w trybie sandbox - płatności są testowe.")
        if (settings.STRIPE_MODE == "live") != (invoicing.mode() == "live"):
            warn(
                f"Stripe ({settings.STRIPE_MODE}) i inFakt ({invoicing.mode()}) "
                "w różnych trybach - prawdziwe płatności dostaną testowe "
                "faktury (albo odwrotnie)."
            )
        if not invoicing.enabled() and gateway.enabled():
            warn("Płatności działają, ale inFakt nie - faktury VAT nie powstaną.")
        if settings.GUS_MODE != "production" or not gus.enabled():
            warn("GUS w trybie test (albo bez klucza) - dane firm są testowe.")
        missing = [
            field
            for field in legal.PLACEHOLDERS
            # The privacy address falls back to the contact one.
            if field != "privacy_email" and not settings.LEGAL_ENTITY.get(field)
        ]
        if missing:
            warn(
                "Puste dane w dokumentach prawnych (.env LEGAL_*): "
                + ", ".join(missing)
            )

        stuck = VatInvoice.objects.filter(
            status__in=[VatInvoiceStatus.PENDING, VatInvoiceStatus.PROCESSING],
            created_at__lt=timezone.now() - timedelta(hours=1),
        ).count()
        failed = VatInvoice.objects.filter(status=VatInvoiceStatus.FAILED).count()
        if stuck:
            warn(f"{stuck} faktur czeka ponad godzinę - czy działa worker i beat?")
        if failed:
            warn(f"{failed} faktur z błędem - /admin/ → Faktury VAT.")
        unsent = BillingNotice.objects.filter(
            sent_at__isnull=True,
            created_at__lt=timezone.now() - timedelta(minutes=15),
        ).count()
        if unsent:
            warn(f"{unsent} e-maili o płatnościach nie wysłanych od 15 min - beat?")
