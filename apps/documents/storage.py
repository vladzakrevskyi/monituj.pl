from django.conf import settings
from django.core.files.storage import FileSystemStorage

private_storage = FileSystemStorage(location=str(settings.PRIVATE_STORAGE_ROOT))
