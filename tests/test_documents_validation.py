import pytest

from apps.common.exceptions import ValidationAppError
from apps.documents.validation import validate_upload
from tests.conftest import make_fake_exe_upload, make_pdf_upload, make_png_upload


def test_validate_upload_accepts_valid_pdf():
    result = validate_upload(make_pdf_upload())

    assert result.extension == "pdf"
    assert result.mime_type == "application/pdf"
    assert len(result.checksum) == 64


def test_validate_upload_accepts_valid_png():
    result = validate_upload(make_png_upload())

    assert result.mime_type == "image/png"


def test_validate_upload_rejects_disallowed_extension():
    upload = make_pdf_upload(name="dokument.exe")

    with pytest.raises(ValidationAppError) as exc_info:
        validate_upload(upload)
    assert exc_info.value.code == "EXTENSION_NOT_ALLOWED"


def test_validate_upload_rejects_spoofed_content_disguised_as_pdf():
    upload = make_fake_exe_upload(name="faktura.pdf")

    with pytest.raises(ValidationAppError) as exc_info:
        validate_upload(upload)
    assert exc_info.value.code == "MIME_NOT_ALLOWED"


def test_validate_upload_rejects_oversized_file():
    upload = make_pdf_upload()
    upload.size = 21 * 1024 * 1024

    with pytest.raises(ValidationAppError) as exc_info:
        validate_upload(upload)
    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_validate_upload_rejects_empty_file():
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("pusty.pdf", b"", content_type="application/pdf")

    with pytest.raises(ValidationAppError) as exc_info:
        validate_upload(upload)
    assert exc_info.value.code == "EMPTY_FILE"


def test_validate_upload_handles_path_traversal_attempt_in_filename():
    upload = make_pdf_upload(name="../../etc/passwd.pdf")

    result = validate_upload(upload)

    assert result.extension == "pdf"
