from django.core.management.base import BaseCommand

from apps.documents.encryption import generate_key


class Command(BaseCommand):
    help = "Prints a new random master key for DOCUMENTS_ENCRYPTION_KEY."

    def handle(self, *args, **options):
        self.stdout.write(generate_key())
