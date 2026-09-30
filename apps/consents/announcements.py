"""Announcing new versions of the legal documents by email.

notify_legal_update publishes the announcement (what changes, in a few
words) and emails every account that hasn't accepted the new versions.
Whoever joins later while it is current gets the same email as soon as
their address is confirmed (welcome) - they sign up on the version in force
and are asked to accept the new one on its day, like everyone, so they must
hear about it too. The hourly send_legal_announcements task catches anyone
missed. Nobody gets the same announcement twice (LegalUpdateNotice)."""

from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.models import User
from apps.common import legal
from apps.common.site import absolute_url
from apps.consents.models import LegalAcceptance, LegalAnnouncement, LegalUpdateNotice
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService


def announced_key():
    """The versions announced - the key that stops a second email."""
    return "|".join(f"{key}:{legal.version(key)}" for key in legal.ACCEPTED)


def publish(changes):
    """Stores what changes for the current versions (a new run updates it)."""
    announcement, _ = LegalAnnouncement.objects.update_or_create(
        announced=announced_key(), defaults={"changes": changes}
    )
    return announcement


def recipients(user_ids=None):
    """[(user, documents they haven't accepted in their current version)] -
    active, confirmed, not demo, not told about these versions yet
    (limited to user_ids when given)."""
    key = announced_key()
    accepted = {}
    acceptances = LegalAcceptance.objects.all()
    if user_ids is not None:
        acceptances = acceptances.filter(user_id__in=user_ids)
    for user_id, document, version in acceptances.values_list(
        "user_id", "document", "version"
    ):
        accepted.setdefault(user_id, set()).add((document, version))
    users = (
        User.objects.filter(is_active=True, email_verified_at__isnull=False)
        .exclude(demo_account__isnull=False)
        .exclude(pk__in=LegalUpdateNotice.objects.filter(version=key).values("user_id"))
        .order_by("pk")
    )
    if user_ids is not None:
        users = users.filter(pk__in=user_ids)
    found = []
    for user in users.iterator():
        new = [
            document
            for document in legal.ACCEPTED
            if (document, legal.version(document)) not in accepted.get(user.pk, set())
        ]
        if new:
            found.append((user, new))
    return found


def welcome(user):
    """A new, confirmed account during a notice period: the announcement,
    once the account is saved."""
    transaction.on_commit(lambda: send(user_ids=[user.pk]))


def send(user_ids=None):
    """Emails the current announcement to whoever should get it and hasn't.
    Nothing without a published announcement. -> how many were emailed."""
    announcement = LegalAnnouncement.objects.filter(announced=announced_key()).first()
    if announcement is None:
        return 0
    sent = 0
    for user, new in recipients(user_ids):
        try:
            LegalUpdateNotice.objects.create(user=user, version=announcement.announced)
        except IntegrityError:
            continue  # another run got there first
        EmailService.send(
            EmailTemplate.LEGAL_UPDATE,
            to_email=user.email,
            context={
                "changes": announcement.changes,
                "documents": [
                    {
                        "title": legal.DOCUMENTS[key].title,
                        "url": absolute_url(reverse(legal.DOCUMENTS[key].url_name))
                        + ("" if legal.in_force(key) else "?wersja=nowa"),
                        "since": legal.effective_date_display(key),
                    }
                    for key in new
                ],
                "effective_date": legal.effective_date_display(
                    max(new, key=legal.effective_date)
                ),
                "settings_url": absolute_url(reverse("accounts:settings")),
            },
        )
        sent += 1
    return sent
