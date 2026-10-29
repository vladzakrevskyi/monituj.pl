"""Every stored document through the antivirus scanner - once, after the
scanner is switched on, for the files that came in before it (README,
"Skaner antywirusowy"). Files with macros count as findings too.

    python manage.py scan_documents

Nothing is deleted or changed: what was found is printed and mailed to
SECURITY_EMAIL, with the request it belongs to - the decision is yours.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError

from apps.documents import antivirus
from apps.documents.encryption import DecryptionError
from apps.documents.models import Document
from apps.documents.storage import read_document_file


def _where(document):
    request_obj = document.request_item.request
    return (
        f"dokument #{document.pk} „{document.original_filename}” - prośba "
        f"#{request_obj.pk} „{request_obj.name}”, konto "
        f"{request_obj.created_by.email}, odbiorca {request_obj.client.email}"
    )


class Command(BaseCommand):
    help = "Scans every stored document with the antivirus scanner."

    def handle(self, *args, **options):
        if not antivirus.enabled():
            raise CommandError("Set CLAMAV_HOST first (README: Skaner antywirusowy).")
        if not antivirus.ping():
            raise CommandError("The antivirus scanner doesn't answer.")
        documents = Document.objects.filter(
            anonymized_at__isnull=True, request_item__isnull=False
        ).select_related(
            "request_item__request__client", "request_item__request__created_by"
        )
        total = documents.count()
        found, unreadable = [], []
        for number, document in enumerate(documents.iterator(), start=1):
            try:
                content = read_document_file(document)
            except DecryptionError, ImproperlyConfigured, OSError, ValueError:
                unreadable.append(_where(document))
                continue
            try:
                name = antivirus.scan(content)
            except antivirus.ScannerUnavailable as exc:
                raise CommandError(
                    f"The scanner stopped answering after {number - 1} of "
                    f"{total} files: {exc}. Run the command again."
                ) from exc
            if name is not None:
                found.append(f"{name}: {_where(document)}")
                self.stdout.write(self.style.ERROR(f"  ! {found[-1]}"))
            if number % 100 == 0:
                self.stdout.write(f"  {number}/{total}")

        lines = [
            f"Sprawdzono plików: {total - len(unreadable)} z {total}.",
            f"Znaleziono: {len(found)}.",
            *[f"- {line}" for line in found],
        ]
        if unreadable:
            lines += [f"Nie udało się odczytać: {len(unreadable)}."]
            lines += [f"- {line}" for line in unreadable]
        if found:
            lines += [
                "",
                "Pliki nie zostały usunięte. Plik z makrami (Heuristics.OLE2."
                "ContainsMacros) to zwykle zwykły arkusz - ale nie otwieraj go "
                "z włączonymi makrami. Plik z wirusem usuń w panelu prośby albo "
                "poproś właściciela konta, żeby to zrobił.",
            ]
        report = "\n".join(lines)
        self.stdout.write(report)
        if settings.SECURITY_EMAIL:
            EmailMessage(
                subject=f"{settings.EMAIL_SUBJECT_PREFIX}Skanowanie plików: "
                f"znaleziono {len(found)}",
                body=report,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.SECURITY_EMAIL],
            ).send()
