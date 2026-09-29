import io

import pytest
from django.core.management import call_command

from apps.consents.models import LegalVersion


def _run():
    out = io.StringIO()
    call_command("post_deploy", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_post_deploy_archives_documents_and_reports(settings):
    settings.MAINTENANCE_MODE = True

    report = _run()

    assert "Dokumenty prawne: 5 nowych wersji w archiwum" in report
    assert LegalVersion.objects.count() == 5
    assert "MAINTENANCE_MODE=True" in report
    # Run again: nothing new, nothing breaks.
    assert "Dokumenty prawne: bez zmian" in _run()


@pytest.mark.django_db
def test_post_deploy_never_fails_the_deploy(monkeypatch):
    from apps.common.management.commands import post_deploy

    def broken():
        raise RuntimeError("archive down")

    monkeypatch.setattr(post_deploy, "archive_all", broken)

    report = _run()

    assert "✗ Dokumenty prawne: archive down" in report
    assert "Do sprawdzenia" in report


@pytest.mark.django_db
def test_post_deploy_syncs_stripe_when_payments_are_on(monkeypatch):
    from apps.common.management.commands import post_deploy

    calls = []
    monkeypatch.setattr(post_deploy.gateway, "enabled", lambda: True)
    monkeypatch.setattr(
        post_deploy.gateway, "keys", lambda: {"webhook_secret": "whsec_x"}
    )
    monkeypatch.setattr(
        post_deploy, "call_command", lambda *args, **kwargs: calls.append(args)
    )
    monkeypatch.setattr(post_deploy.invoicing, "enabled", lambda: False)

    report = _run()

    assert calls == [("stripe_setup",)]
    assert "Stripe: zsynchronizowane" in report
