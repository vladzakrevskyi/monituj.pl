"""Request templates: the owner's own (RequestTemplate) and the ready ones
(template_library). A template fills the new request form - name, list,
deadline and settings, never the clients.

How many own templates an account keeps depends on its plan
(plans.Plan.templates). That limit is part of the Regulamin dated
TEMPLATE_LIMITS_SINCE: until that version is in force, everyone has the
technical limit only - so forgetting to publish it never limits anyone."""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.common.exceptions import ValidationAppError
from apps.requests import template_library
from apps.requests.models import RequestTemplate

# The Regulamin that introduced per-plan template limits applies from this
# day (LEGAL_TERMS_DATE must be this or later).
TEMPLATE_LIMITS_SINCE = date(2026, 10, 15)
# The most any account keeps (Pro's limit) - and everyone's before then.
TECHNICAL_LIMIT = 50
MAX_ITEMS = 50
DEADLINE_CHOICES = ("7", "14", "day10", "days", "none")
# ?szablon=<slug> on the way to signing up, kept until the account exists.
SIGNUP_SESSION_KEY = "signup_template"


# --- limits ------------------------------------------------------------------


def limits_in_force():
    from apps.common import legal

    return legal.in_force(legal.TERMS) and (
        legal.effective_date(legal.TERMS) >= TEMPLATE_LIMITS_SINCE
    )


def usage(owner):
    """{"used", "limit", "plan", "left", "at_limit"} for the templates page
    and the form. plan is None when the plan doesn't decide the limit."""
    from apps.billing.services import state_for

    used = RequestTemplate.objects.filter(owner=owner).count()
    plan = None
    limit = TECHNICAL_LIMIT
    if limits_in_force():
        state = state_for(owner)
        if state.source != "demo":
            plan = state.plan
            limit = plan.templates
    return {
        "used": used,
        "limit": limit,
        "plan": plan,
        "left": max(limit - used, 0),
        "at_limit": used >= limit,
    }


def check_can_add(owner):
    from apps.billing.plans import templates_phrase

    current = usage(owner)
    if not current["at_limit"]:
        return
    if current["plan"] is not None:
        message = (
            f"W planie {current['plan'].name} zapiszesz "
            f"{templates_phrase(current['limit'])}. Usuń szablon, którego nie "
            "używasz, albo zmień plan."
        )
    else:
        message = (
            f"Możesz mieć najwyżej {templates_phrase(current['limit'])}. Usuń "
            "szablon, którego nie używasz."
        )
    raise ValidationAppError(message, code="TEMPLATE_LIMIT")


# --- saving ------------------------------------------------------------------


def _clean(title, name, item_names):
    title = " ".join((title or "").split())[:120]
    name = " ".join((name or "").split())[:255]
    items = [n.strip()[:255] for n in item_names if n and n.strip()]
    items = list(dict.fromkeys(items))
    if not title:
        raise ValidationAppError("Podaj nazwę szablonu.", code="TEMPLATE_TITLE")
    if not items:
        raise ValidationAppError(
            "Dodaj co najmniej jeden dokument do listy.", code="TEMPLATE_ITEMS"
        )
    if len(items) > MAX_ITEMS:
        raise ValidationAppError(
            f"Szablon może mieć najwyżej {MAX_ITEMS} dokumentów.",
            code="TEMPLATE_ITEMS",
        )
    return title, name or title, items


def check_title_free(owner, title, template=None):
    taken = RequestTemplate.objects.filter(owner=owner, title__iexact=title)
    if template is not None:
        taken = taken.exclude(pk=template.pk)
    if taken.exists():
        raise ValidationAppError(
            f"Masz już szablon „{title}”. Nadaj temu inną nazwę.",
            code="TEMPLATE_TITLE_TAKEN",
        )


def save(
    owner,
    *,
    title,
    name,
    description,
    item_names,
    deadline_choice,
    deadline_days=None,
    settings=None,
    template=None,
):
    """Creates (template=None) or updates an own template. settings: the
    reminder and retention fields, as the request form gives them."""
    title, name, items = _clean(title, name, item_names)
    if deadline_choice not in DEADLINE_CHOICES:
        deadline_choice = "14"
    if deadline_choice != "days":
        deadline_days = None
    elif not deadline_days:
        raise ValidationAppError("Podaj liczbę dni.", code="TEMPLATE_DEADLINE")
    if template is None:
        check_can_add(owner)
        template = RequestTemplate(owner=owner)
    check_title_free(owner, title, template if template.pk else None)
    template.title = title
    template.name = name
    template.description = (description or "").strip()
    template.item_names = items
    template.deadline_choice = deadline_choice
    template.deadline_days = deadline_days
    for field, value in (settings or {}).items():
        setattr(template, field, value)
    try:
        with transaction.atomic():
            template.save()
    except IntegrityError as exc:
        raise ValidationAppError(
            f"Masz już szablon „{title}”. Nadaj temu inną nazwę.",
            code="TEMPLATE_TITLE_TAKEN",
        ) from exc
    return template


def free_title(owner, title):
    """The title, or "title (2)", "(3)"... when the owner already has it."""
    title = " ".join(title.split())[:110]
    taken = {
        t.lower()
        for t in RequestTemplate.objects.filter(owner=owner).values_list(
            "title", flat=True
        )
    }
    candidate, number = title, 2
    while candidate.lower() in taken:
        candidate = f"{title} ({number})"
        number += 1
    return candidate


def _settings_of(source):
    return {
        field: getattr(source, field)
        for field in (
            "reminders_enabled",
            "first_reminder_after_days",
            "reminder_frequency_days",
            "max_reminders",
            "retention_days",
        )
    }


def from_request(owner, request_obj):
    """ "Zapisz jako szablon" on a request: its list, deadline and settings.
    A request made by a recurring one keeps the recurring name
    ("Dokumenty za {miesiąc}"), not this month's."""
    schedule = request_obj.recurring
    name = schedule.name if schedule is not None else request_obj.name
    deadline_choice, deadline_days = "none", None
    if request_obj.deadline:
        days = (
            timezone.localtime(request_obj.deadline).date()
            - timezone.localtime(request_obj.created_at).date()
        ).days
        if days in (7, 14):
            deadline_choice = str(days)
        elif days > 0:
            deadline_choice, deadline_days = "days", min(days, 365)
    return save(
        owner,
        title=free_title(owner, request_obj.name),
        name=name,
        description=request_obj.description,
        item_names=list(
            request_obj.items.order_by("id").values_list("name", flat=True)
        ),
        deadline_choice=deadline_choice,
        deadline_days=deadline_days,
        settings=_settings_of(request_obj),
    )


def copy_ready(owner, ready):
    """ "Zapisz jako mój" on a ready template - a copy to change freely."""
    return save(
        owner,
        title=free_title(owner, ready.title),
        name=ready.name,
        description=ready.description,
        item_names=ready.item_names,
        deadline_choice=ready.deadline,
    )


# --- using -------------------------------------------------------------------


def find(owner, key):
    """An own template (its id) or a ready one (its slug) - or None."""
    key = (key or "").strip()
    if not key:
        return None
    if key.isdigit():
        if owner is None or not owner.is_authenticated:
            return None
        return RequestTemplate.objects.filter(owner=owner, pk=int(key)).first()
    return template_library.get(key)


def key_of(template):
    return str(template.pk) if isinstance(template, RequestTemplate) else template.slug


def form_values(template, today):
    """What the template puts in the new request form: (initial, item names).
    A deadline counted in days becomes a date for a one-off request - and
    stays as days if the person switches to a recurring one."""
    if isinstance(template, RequestTemplate):
        choice, days = template.deadline_choice, template.deadline_days
    else:
        choice, days = template.deadline, None
    initial = {
        "name": template.name,
        "description": template.description,
        "deadline_choice": choice,
    }
    if choice == "days" and days:
        initial.update(
            deadline_choice="date",
            deadline=today + timedelta(days=days),
            deadline_days=days,
        )
    if isinstance(template, RequestTemplate):
        from apps.requests.forms import RequestForm, reminder_preset_of

        initial.update(
            reminder_preset=reminder_preset_of(
                template.reminders_enabled,
                template.first_reminder_after_days,
                template.reminder_frequency_days,
                template.max_reminders,
            ),
            first_reminder_after_days=template.first_reminder_after_days,
            reminder_frequency_days=template.reminder_frequency_days,
            max_reminders=template.max_reminders,
            **RequestForm.retention_initial(template.retention_days),
        )
    return initial, list(template.item_names)


def mark_used(template):
    if isinstance(template, RequestTemplate):
        RequestTemplate.objects.filter(pk=template.pk).update(
            last_used_at=timezone.now()
        )


def picker(owner):
    """The form's template list: own ones first (recently used on top), then
    the ready ones by industry."""
    from apps.common.content import SEGMENTS

    own = []
    if owner is not None and owner.is_authenticated:
        own = list(
            RequestTemplate.objects.filter(owner=owner).order_by(
                "-last_used_at", "title"
            )
        )
    groups = [
        {"title": segment["title"], "templates": template_library.for_segment(slug)}
        for segment in SEGMENTS
        for slug in [segment["slug"]]
        if template_library.for_segment(slug)
    ]
    return {"own": own, "ready_groups": groups}


def deadline_label(template):
    choice = (
        template.deadline_choice
        if isinstance(template, RequestTemplate)
        else template.deadline
    )
    if choice in ("7", "14"):
        return f"termin {choice} dni"
    if choice == "day10":
        return "termin do 10. dnia miesiąca"
    if choice == "days" and getattr(template, "deadline_days", None):
        return f"termin {template.deadline_days} dni"
    return "bez terminu"


# --- signing up with a template ----------------------------------------------


def remember_for_signup(request):
    """?szablon=<slug> on the way to signing up (the library's buttons)."""
    slug = request.GET.get("szablon", "")
    if template_library.get(slug):
        request.session[SIGNUP_SESSION_KEY] = slug


def signup_template_url(request):
    """The new request form with the template picked before signing up -
    once; None if none was."""
    slug = request.session.pop(SIGNUP_SESSION_KEY, None)
    if not slug or not template_library.get(slug):
        return None
    return f"{reverse('requests:create')}?szablon={slug}"
