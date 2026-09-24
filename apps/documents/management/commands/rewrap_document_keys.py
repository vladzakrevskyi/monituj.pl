"""After changing DOCUMENTS_ENCRYPTION_KEY (old one moved to
DOCUMENTS_ENCRYPTION_OLD_KEYS): re-encrypts every file's own key with the
new master key. The files themselves are not touched.

    python manage.py rewrap_document_keys
"""

from django.core.management.base import BaseCommand, CommandError

from apps.documents import encryption
from apps.documents.models import Document


class Command(BaseCommand):
    help = "Re-wraps per-file keys with the current master key."

    def handle(self, *args, **options):
        if not encryption.enabled():
            raise CommandError("Set DOCUMENTS_ENCRYPTION_KEY first.")
        current_id = encryption.current_key_id()
        current_key = encryption._keyring()[0]
        done = 0
        stale = Document.objects.exclude(wrapped_key="").exclude(
            encryption_key_id=current_id
        )
        for document in stale.iterator():
            file_key = encryption.unwrap(
                document.wrapped_key, document.encryption_key_id
            )
            Document.objects.filter(
                pk=document.pk, encryption_key_id=document.encryption_key_id
            ).update(
                wrapped_key=encryption.wrap(file_key, current_key),
                encryption_key_id=current_id,
            )
            done += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Re-wrapped {done} keys. The old master key can now be removed."
            )
        )
