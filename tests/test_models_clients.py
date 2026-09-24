import pytest
from django.core.exceptions import ValidationError

from apps.clients.models import Client


@pytest.mark.django_db
def test_client_str_returns_name(client_record):
    assert str(client_record) == "Acme Sp. z o.o."


@pytest.mark.django_db
def test_client_requires_owner():
    client = Client(name="No owner", email="none@example.com")

    with pytest.raises(ValidationError):
        client.full_clean()
