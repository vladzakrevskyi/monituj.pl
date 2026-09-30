"""The archive of legal documents' wordings (LegalVersion).

A wording is archived the first time it matters - someone accepts it or
buys a plan on it - and once a day for every document, so even a policy
nobody has to accept (cookies) keeps its history. The archive also serves
the notice period: a new version dated ahead is on the site at once, but
until its day the one in force is the latest earlier archived wording
(in_force) - the pages, sign-ups and purchases use that one. The archive is keyed by
the text itself (SHA-256), not by the date: a text edited without a new
date still gets its own row, and the team is told."""

import hashlib
import logging

from django.db import IntegrityError, transaction

from apps.common import legal
from apps.consents.models import LegalVersion

logger = logging.getLogger("monituj")


def current(key):
    """The archived row of the document's current wording - added now if the
    wording is new."""
    html = legal.render_body(key)
    sha256 = hashlib.sha256(html.encode()).hexdigest()
    found = LegalVersion.objects.filter(document=key, sha256=sha256).first()
    if found is not None:
        return found
    version = legal.version(key)
    try:
        with transaction.atomic():
            row = LegalVersion.objects.create(
                document=key, version=version, sha256=sha256, html=html
            )
    except IntegrityError:
        # Archived at the same moment by another request.
        return LegalVersion.objects.get(document=key, sha256=sha256)
    if LegalVersion.objects.filter(document=key, version=version).count() > 1:
        _alert_changed_without_new_version(key, version)
    return row


def archive_all():
    """Archives every document's current wording. Returns how many were
    new."""
    before = LegalVersion.objects.count()
    for key in legal.DOCUMENTS:
        current(key)
    return LegalVersion.objects.count() - before


def _alert_changed_without_new_version(key, version):
    from apps.billing import notices

    title = legal.DOCUMENTS[key].title
    logger.warning("Legal document %s changed without a new version", key)
    notices.alert_team(
        f"{title}: zmieniona treść bez nowej daty",
        [
            f"Treść dokumentu „{title}” różni się od zapisanej w archiwum, "
            f"a wersja (data) jest ta sama: {version}.",
            "Jeśli to zmiana merytoryczna, nadaj dokumentowi nową datę w .env "
            "(LEGAL_TERMS_DATE, LEGAL_DPA_DATE, LEGAL_PRIVACY_DATE, "
            "LEGAL_COOKIES_DATE, LEGAL_WITHDRAWAL_DATE) i - dla Regulaminu i "
            "umowy powierzenia - uprzedź użytkowników (notify_legal_update). "
            "Obie wersje tekstu są w /admin/ → „Wersje dokumentów”.",
            "To samo się dzieje, gdy zmienisz dane w .env widoczne w "
            "dokumentach (np. dostawcę hostingu).",
        ],
        key=f"legal-drift:{key}:{version}:{LegalVersion.objects.filter(document=key).count()}",
    )


def in_force(key):
    """The wording in force today. Normally the current one; while a new
    version dated ahead waits for its day (the notice period), the latest
    archived earlier one - the pages show it, and signing up or buying then
    happens on it. None only if no earlier wording was ever archived."""
    if legal.in_force(key):
        return current(key)
    return (
        LegalVersion.objects.filter(document=key, version__lt=legal.version(key))
        .order_by("-version", "-created_at")
        .first()
    )


def upcoming(key):
    """The new wording waiting for its day - or None when the document has
    no notice period running (or nothing earlier to compare with)."""
    if legal.in_force(key) or in_force(key) is None:
        return None
    return current(key)


def wordings(keys):
    """{document: {"version", "sha256"[, "next": {"version", "sha256"}]}}
    for the given documents - what is stored with a purchase: the wording in
    force, and the one announced to follow it."""
    found = {}
    for key in keys:
        row = in_force(key) or current(key)
        found[key] = {"version": row.version, "sha256": row.sha256}
        following = upcoming(key)
        if following is not None:
            found[key]["next"] = {
                "version": following.version,
                "sha256": following.sha256,
            }
    return found
