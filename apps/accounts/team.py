"""Teams and workspaces.

Everyone has their own account - their clients, requests, templates, plan.
A firm's owner can invite people to their account (a TeamMembership); one
person may be in any number of teams and still keep their own account.
The panel always works in one of them - the workspace, chosen with the
switcher and kept in the session (WorkspaceMiddleware sets request.account).
Data is looked up by request.account, never across workspaces; request.user
stays who did it, and the request's history names them.

Inside someone else's workspace a member does everything the owner does,
except what is the owner's: the team, the plan and payments, the firm's
details shown to recipients, deleting the account.

Seats come with the plan (plans.Plan.seats, the owner included). With more
people than seats - a lower plan, the end of the trial - nothing is
deleted, but members over the limit wait outside that workspace until the
owner changes the plan or pauses someone else: otherwise a month's trial
would give a team for free forever. Without the owner's choice the ones who
joined last wait."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as django_login
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import TeamInvitation, TeamMembership, User
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common import throttle
from apps.common.exceptions import ValidationAppError
from apps.common.security import generate_public_token, hash_token
from apps.common.site import absolute_url

INVITATION_DAYS = 7
INVITATIONS_PER_DAY = 30
SESSION_KEY = "workspace"
# An invitation link opened before signing in - joined right after any
# sign-in (password, Google, two-step), wherever that sign-in lands.
PENDING_KEY = "team_invitation"


def seats(owner):
    """People the plan allows, the owner included."""
    from apps.billing.services import plan_for
    from apps.demo.models import is_demo_user

    if is_demo_user(owner):
        return 1
    return plan_for(owner)[0].seats


def members(owner):
    """The owner's team, as memberships (with .user), oldest first."""
    return TeamMembership.objects.filter(owner=owner).select_related("user")


def pending_invitations(owner):
    return owner.team_invitations.filter(
        accepted_at__isnull=True, expires_at__gt=timezone.now()
    )


def with_access(owner):
    """The memberships that may work now: not paused, within the seats -
    first come, first served."""
    allowed = [m for m in members(owner) if m.access]
    return allowed[: max(seats(owner) - 1, 0)]


def usage(owner):
    """{"seats", "used", "free", "over"} - used counts the owner, members
    with access turned on and invitations still waiting."""
    total = seats(owner)
    active = sum(1 for m in members(owner) if m.access)
    used = 1 + active + pending_invitations(owner).count()
    return {
        "seats": total,
        "used": used,
        "free": max(total - used, 0),
        "over": max(1 + active - total, 0),
    }


def firm_name(owner):
    return owner.display_name or owner.email


# --- workspaces --------------------------------------------------------------------


def membership(user, owner):
    if user.pk == owner.pk:
        return None
    return TeamMembership.objects.filter(user=user, owner=owner).first()


def has_access(found):
    """May this membership work in its workspace right now?"""
    return any(m.pk == found.pk for m in with_access(found.owner))


def can_work_in(user, owner_id):
    """Is owner_id the user's own account or a team they may work in now?"""
    if user.pk == owner_id:
        return True
    found = TeamMembership.objects.filter(user=user, owner_id=owner_id).first()
    return found is not None and has_access(found)


def workspaces(user):
    """[{"owner", "name", "own"}] - the user's own account first."""
    found = [{"owner": user, "name": "Moje konto", "own": True}]
    for m in user.memberships.select_related("owner").order_by("joined_at"):
        found.append({"owner": m.owner, "name": firm_name(m.owner), "own": False})
    return found


def resolve(request):
    """(account, membership) for this request - the workspace in the
    session if the user is still in it, else their own account."""
    user = request.user
    chosen = request.session.get(SESSION_KEY)
    if chosen and chosen != user.pk:
        found = (
            TeamMembership.objects.select_related("owner")
            .filter(user=user, owner_id=chosen)
            .first()
        )
        if found is not None:
            return found.owner, found
        request.session.pop(SESSION_KEY, None)
    return user, None


def switch(request, owner_id):
    """Opens a workspace - the user's own or a team they belong to."""
    user = request.user
    if owner_id != user.pk and not user.memberships.filter(owner_id=owner_id).exists():
        raise ValidationAppError("Nie należysz do tego zespołu.")
    if owner_id == user.pk:
        request.session.pop(SESSION_KEY, None)
    else:
        request.session[SESSION_KEY] = owner_id
    request.account = User.objects.get(pk=owner_id)


def follow(request, owner):
    """A link (e.g. from an email) to something in another of the user's
    workspaces: switch to it and say so. -> True when switched."""
    if owner.pk == request.account.pk or not can_work_in(request.user, owner.pk):
        return False
    switch(request, owner.pk)
    name = "Moje konto" if owner.pk == request.user.pk else firm_name(owner)
    messages.info(request, f"Przełączono na: {name}.")
    return True


# What can't be undone and wipes a lot at once - deleting in bulk, or a client
# with all their history - is the owner's alone: one wrong click by a team
# member must not empty the firm.
OWNER_ONLY_MESSAGE = (
    "Usuwanie wielu próśb lub klientów naraz i klienta z całą historią może "
    "wykonać tylko właściciel konta."
)


def is_owner(request):
    """Is the user working in their own account (not a team's)?"""
    return getattr(request, "membership", None) is None


# --- inviting ---------------------------------------------------------------------


def why_cannot_join(user, owner):
    """Why this account can't join the owner's team - or None."""
    from apps.demo.models import is_demo_user

    if is_demo_user(user):
        return "To konto demonstracyjne."
    if user.pk == owner.pk:
        return "To Twoje konto - jesteś jego właścicielem."
    if TeamMembership.objects.filter(user=user, owner=owner).exists():
        return "Ta osoba jest już w tym zespole."
    return None


@transaction.atomic
def invite(owner, email, django_request=None):
    """Mails an invitation; a new one to the same address replaces the
    waiting one. -> the invitation."""
    from apps.notifications.models import EmailTemplate
    from apps.notifications.services import EmailService

    email = User.objects.normalize_email(email.strip())
    existing = User.objects.filter(email__iexact=email).first()
    if email.lower() == owner.email.lower():
        raise ValidationAppError("To Twój adres - jesteś już w zespole.")
    if existing is not None:
        reason = why_cannot_join(existing, owner)
        if reason:
            raise ValidationAppError(reason, code="CANNOT_JOIN")
    pending_invitations(owner).filter(email__iexact=email).delete()
    if usage(owner)["free"] < 1:
        raise ValidationAppError(_no_seat_message(owner), code="NO_SEAT")
    throttle.consume(
        f"team-invite:{owner.pk}",
        INVITATIONS_PER_DAY,
        throttle.DAY,
        "Wysłano dziś bardzo dużo zaproszeń. Spróbuj ponownie jutro.",
    )
    raw = generate_public_token()
    invitation = TeamInvitation.objects.create(
        owner=owner,
        email=email,
        token_hash=hash_token(raw),
        expires_at=timezone.now() + timedelta(days=INVITATION_DAYS),
    )
    AuditService.log(
        AuditEvent.TEAM_INVITED,
        actor=owner,
        target=owner,
        request=django_request,
        metadata={"email": email},
    )
    EmailService.send(
        EmailTemplate.TEAM_INVITATION,
        to_email=email,
        context={
            "firm": firm_name(owner),
            "owner_email": owner.email,
            "link": absolute_url(reverse("accounts:team-join", args=[raw])),
            "days": INVITATION_DAYS,
            "has_account": existing is not None,
        },
        reply_to=[owner.email],
    )
    return invitation


def _no_seat_message(owner):
    from apps.billing import plans
    from apps.billing.services import plan_for

    plan = plan_for(owner)[0]
    return (
        f"Plan {plan.name} obejmuje {plans.seats_phrase(plan.seats)} - nie ma "
        "wolnego miejsca. Zmień plan albo usuń zaproszenie lub osobę z zespołu."
    )


def find_invitation(raw):
    """The invitation behind a link, if it can still be used."""
    return (
        TeamInvitation.objects.select_related("owner")
        .filter(
            token_hash=hash_token(raw or ""),
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )


def cancel(owner, invitation_id):
    owner.team_invitations.filter(pk=invitation_id, accepted_at__isnull=True).delete()


# --- joining -----------------------------------------------------------------------


def _check_seat(invitation):
    """The seat was held by the invitation - unless the plan shrank since."""
    owner = invitation.owner
    taken = 1 + sum(1 for m in members(owner) if m.access)
    if taken >= seats(owner):
        raise ValidationAppError(
            "W planie tego zespołu nie ma już wolnego miejsca. Poproś osobę, "
            "która Cię zaprosiła, o zmianę planu.",
            code="NO_SEAT",
        )


def _join(user, invitation, django_request):
    found = TeamMembership.objects.create(owner=invitation.owner, user=user)
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    AuditService.log(
        AuditEvent.TEAM_JOINED,
        actor=user,
        target=invitation.owner,
        request=django_request,
    )
    # Straight into the team's workspace.
    if django_request is not None and hasattr(django_request, "session"):
        django_request.session[SESSION_KEY] = invitation.owner.pk
    return found


@transaction.atomic
def join_as_new(invitation, name, password, django_request):
    """A new account straight into the team - the address is confirmed by the
    link it came from. The person gets their own account too, like
    everyone."""
    from apps.accounts.services import _validate_password_strength
    from apps.consents.models import AcceptanceMethod
    from apps.consents.services import record_acceptance

    existing = User.objects.filter(email__iexact=invitation.email).first()
    if existing is not None and existing.email_verified_at is not None:
        raise ValidationAppError(
            "Konto z tym adresem już istnieje - zaloguj się, aby dołączyć.",
            code="EMAIL_TAKEN",
        )
    _check_seat(invitation)
    _validate_password_strength(password)
    # Joined here - not again by the sign-in below.
    django_request.session.pop(PENDING_KEY, None)
    now = timezone.now()
    if existing is not None:
        # Signed up once and never confirmed the address: the invitation
        # link, mailed there, confirms it - and the password set now
        # replaces any earlier one, like a password reset.
        user = existing
        user.set_password(password)
        user.display_name = user.display_name or name.strip()[:255]
        user.email_verified_at = now
        user.save(update_fields=["password", "display_name", "email_verified_at"])
        AuditService.log(
            AuditEvent.EMAIL_VERIFIED, actor=user, target=user, request=django_request
        )
    else:
        user = User.objects.create_user(
            email=invitation.email,
            password=password,
            display_name=name.strip()[:255],
            email_verified_at=now,
            terms_accepted_at=now,
            privacy_policy_accepted_at=now,
        )
        AuditService.log(
            AuditEvent.USER_REGISTERED, actor=user, target=user, request=django_request
        )
    record_acceptance(user, AcceptanceMethod.TEAM_INVITATION, django_request)
    django_login(
        django_request, user, backend="django.contrib.auth.backends.ModelBackend"
    )
    _join(user, invitation, django_request)
    return user


@transaction.atomic
def join_as_existing(invitation, user, django_request):
    if user.email.lower() != invitation.email.lower():
        raise ValidationAppError(
            f"To zaproszenie jest dla {invitation.email}. Wyloguj się i zaloguj "
            "na to konto.",
            code="WRONG_ACCOUNT",
        )
    reason = why_cannot_join(user, invitation.owner)
    if reason:
        raise ValidationAppError(reason, code="CANNOT_JOIN")
    _check_seat(invitation)
    _join(user, invitation, django_request)
    return user


def remember(request, raw):
    """The invitation link opened by someone not signed in yet."""
    request.session[PENDING_KEY] = raw


def join_after_login(sender, request, user, **kwargs):
    """user_logged_in: joins the team whose link was opened before signing
    in - whichever way the sign-in went (the password form, Google, the
    second step), it lands in the team's workspace."""
    if request is None or not hasattr(request, "session"):
        return
    raw = request.session.pop(PENDING_KEY, None)
    invitation = find_invitation(raw) if raw else None
    if invitation is None:
        return
    if TeamMembership.objects.filter(user=user, owner=invitation.owner).exists():
        return
    firm = firm_name(invitation.owner)
    try:
        join_as_existing(invitation, user, request)
    except ValidationAppError as exc:
        messages.warning(
            request,
            f"Zaproszenie do zespołu {firm}: {exc.message}",
            fail_silently=True,
        )
        return
    messages.success(request, f"Dołączono do zespołu {firm}.", fail_silently=True)


# --- managing ----------------------------------------------------------------------


def member_of(owner, membership_id):
    found = members(owner).filter(pk=membership_id).first()
    if found is None:
        raise ValidationAppError("Nie ma takiej osoby w Twoim zespole.")
    return found


def set_access(owner, found, allowed, django_request=None):
    if allowed and not found.access and usage(owner)["free"] < 1:
        raise ValidationAppError(_no_seat_message(owner), code="NO_SEAT")
    found.access = allowed
    found.save(update_fields=["access"])
    AuditService.log(
        AuditEvent.TEAM_ACCESS_CHANGED,
        actor=owner,
        target=found.user,
        request=django_request,
        metadata={"access": allowed},
    )


@transaction.atomic
def remove(owner, found, django_request=None):
    """Out of the team - the person keeps their own account and other teams;
    what they did stays with the firm."""
    from apps.notifications.models import EmailTemplate
    from apps.notifications.services import EmailService

    member = found.user
    found.delete()
    AuditService.log(
        AuditEvent.TEAM_MEMBER_REMOVED,
        actor=owner,
        target=owner,
        request=django_request,
        metadata={"email": member.email},
    )
    EmailService.send(
        EmailTemplate.TEAM_REMOVED,
        to_email=member.email,
        context={"firm": firm_name(owner)},
        reply_to=[owner.email],
    )


@transaction.atomic
def leave(user, owner, django_request=None):
    TeamMembership.objects.filter(user=user, owner=owner).delete()
    AuditService.log(
        AuditEvent.TEAM_LEFT, actor=user, target=owner, request=django_request
    )
