"""Encrypts documents stored before encryption was switched on.

    python manage.py encrypt_documents

Each file is written again, encrypted, under a new name; the database row is
updated and only then the old plaintext file removed. Safe to interrupt and
run again.
"""

import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.documents import encryption
from apps.documents.models import Document
from apps.documents.storage import private_storage, save_document_file


class Command(BaseCommand):
    help = "Encrypts documents stored before encryption was switched on."

    def handle(self, *args, **options):
        if not encryption.enabled():
            raise CommandError("Set DOCUMENTS_ENCRYPTION_KEY first.")
        pending = Document.objects.filter(
            wrapped_key="", anonymized_at__isnull=True
        ).order_by("pk")
        done = 0
        for document in pending.iterator():
            if not private_storage.exists(document.storage_key):
                self.stderr.write(f"Missing file for document {document.pk}, skipped.")
                continue
            with private_storage.open(document.storage_key, "rb") as handle:
                content = handle.read()
            old_key = document.storage_key
            folder, _, name = old_key.rpartition("/")
            extension = name.rpartition(".")[2]
            new_key = f"{folder}/{secrets.token_hex(16)}.{extension}".lstrip("/")
            fields = save_document_file(new_key, content)
            with transaction.atomic():
                updated = Document.objects.filter(
                    pk=document.pk, storage_key=old_key, wrapped_key=""
                ).update(storage_key=new_key, **fields)
            if updated:
                private_storage.delete(old_key)
                done += 1
            else:  # changed meanwhile - leave it for the next run
                private_storage.delete(new_key)
        self.stdout.write(self.style.SUCCESS(f"Encrypted {done} documents."))
