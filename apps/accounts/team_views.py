"""Zespół: the owner's page to invite and manage people, the invitation
link, and leaving the team (apps/accounts/team.py)."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts import team
from apps.billing import plans
from apps.common.exceptions import ApplicationError
from apps.consents.forms import LegalAcceptanceForm
from apps.demo.models import is_demo_user

REQUIRED_MESSAGE = "To pole jest wymagane."


class InviteForm(forms.Form):
    email = forms.EmailField(
        label="Adres e-mail osoby z zespołu",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
        widget=forms.EmailInput(attrs={"placeholder": "np. anna@biuro.pl"}),
    )


class JoinForm(LegalAcceptanceForm):
    name = forms.CharField(
        label="Imię i nazwisko",
        max_length=255,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    password = forms.CharField(
        label="Hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    password_confirm = forms.CharField(
        label="Powtórz hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )

    field_order = ["name", "password", "password_confirm"]

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("password")
            and cleaned.get("password_confirm")
            and cleaned["password"] != cleaned["password_confirm"]
        ):
            self.add_error("password_confirm", "Hasła nie są identyczne.")
        return cleaned


@login_required
@require_http_methods(["GET", "POST"])
def team_page(request):
    owner = request.user
    form = InviteForm()
    if request.method == "POST":
        if is_demo_user(owner):
            messages.error(request, "W wersji demo nie można zapraszać osób.")
            return redirect("accounts:team")
        action = request.POST.get("action")
        try:
            if action == "invite":
                form = InviteForm(request.POST)
                if form.is_valid():
                    team.invite(owner, form.cleaned_data["email"], request)
                    messages.success(
                        request,
                        f"Wysłaliśmy zaproszenie na {form.cleaned_data['email']}.",
                    )
                    return redirect("accounts:team")
            elif action == "cancel":
                team.cancel(owner, request.POST.get("invitation"))
                messages.success(request, "Zaproszenie zostało usunięte.")
                return redirect("accounts:team")
            elif action in {"pause", "resume", "remove"}:
                found = team.member_of(owner, request.POST.get("member"))
                if action == "remove":
                    email = found.user.email
                    team.remove(owner, found, request)
                    messages.success(request, f"{email} nie należy już do zespołu.")
                else:
                    team.set_access(owner, found, action == "resume", request)
                    messages.success(request, "Zapisano dostęp.")
                return redirect("accounts:team")
        except ApplicationError as exc:
            if action == "invite":
                form.add_error("email", exc.message)
            else:
                messages.error(request, exc.message)
                return redirect("accounts:team")

    access = {m.pk for m in team.with_access(owner)}
    people = [
        {"membership": m, "waiting": m.access and m.pk not in access}
        for m in team.members(owner)
    ]
    plan = _plan(owner)
    return render(
        request,
        "accounts/team.html",
        {
            "form": form,
            "people": people,
            "invitations": team.pending_invitations(owner),
            "usage": team.usage(owner),
            "plan": plan,
            "seats_phrase": plans.seats_phrase(plan.seats),
            "next_plan": next(
                (p for p in plans.PAID_PLANS if p.seats > plan.seats), None
            ),
            "invitation_days": team.INVITATION_DAYS,
        },
    )


def _plan(owner):
    from apps.billing.services import plan_for

    return plan_for(owner)[0]


@require_http_methods(["GET", "POST"])
def team_join(request, token):
    """The invitation link: a new account straight into the team, or an
    existing one (signed in) joining it."""
    invitation = team.find_invitation(token)
    if invitation is None:
        return render(request, "accounts/team_join.html", {"invalid": True})
    from apps.accounts.models import User

    firm = team.firm_name(invitation.owner)
    user = request.user
    # An account never confirmed can't sign in - it sets a password here.
    exists = User.objects.filter(
        email__iexact=invitation.email, email_verified_at__isnull=False
    ).exists()
    if not user.is_authenticated:
        team.remember(request, token)
    form = JoinForm()
    error = None

    if request.method == "POST":
        try:
            if user.is_authenticated:
                request.session.pop(team.PENDING_KEY, None)
                team.join_as_existing(invitation, user, request)
            else:
                form = JoinForm(request.POST)
                if not form.is_valid():
                    raise _FormInvalid
                team.join_as_new(
                    invitation,
                    form.cleaned_data["name"],
                    form.cleaned_data["password"],
                    request,
                )
            messages.success(request, f"Witaj w zespole {firm}!")
            return redirect("accounts:panel")
        except _FormInvalid:
            pass
        except ApplicationError as exc:
            if exc.code == "WEAK_PASSWORD":
                form.add_error("password", exc.message)
            else:
                error = exc.message

    return render(
        request,
        "accounts/team_join.html",
        {
            "invitation": invitation,
            "firm": firm,
            "form": form,
            "exists": exists,
            "error": error,
            "wrong_account": user.is_authenticated
            and user.email.lower() != invitation.email.lower(),
            "why_not": team.why_cannot_join(user, invitation.owner)
            if user.is_authenticated
            else None,
        },
    )


class _FormInvalid(Exception):
    pass


@login_required
@require_POST
def team_leave(request):
    from apps.accounts.models import User

    owner = User.objects.filter(pk=request.POST.get("owner")).first()
    if owner is None or not request.user.memberships.filter(owner=owner).exists():
        return redirect("accounts:settings")
    team.leave(request.user, owner, request)
    if request.account.pk == owner.pk:
        team.switch(request, request.user.pk)
    messages.success(request, f"Nie należysz już do zespołu {team.firm_name(owner)}.")
    return redirect("accounts:settings")


@login_required
@require_POST
def workspace(request):
    """The switcher: the user's own account or one of their teams."""
    try:
        team.switch(request, int(request.POST.get("owner", 0)))
    except ApplicationError, ValueError:
        messages.error(request, "Nie należysz do tego zespołu.")
    return redirect("accounts:panel")
