"""Zestawienie miesięczne: who sent everything and who still owes something -
client by client, month by month.

A month here is the month a request was sent in, so the view needs no
guessing from names. Each cell sums up a client's requests sent that month:
"komplet", "brakuje 2", "nic nie przesłał", "po terminie" or closed. Questions
have their own list (Pytania) and stay out of it."""

from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from apps.requests.models import Request, RequestItemKind, RequestItemStatus
from apps.requests.services import with_stats

MONTHS = 6

KOMPLET = "komplet"
BRAKUJE = "brakuje"
NIC = "nic"
PO_TERMINIE = "po_terminie"
ZAMKNIETA = "zamknieta"
# Waiting on the client - what "Przypomnij" is for.
OPEN_STATES = {BRAKUJE, NIC, PO_TERMINIE}


@dataclass
class Cell:
    requests: list = field(default_factory=list)
    total: int = 0
    delivered: int = 0
    missing: int = 0
    to_review: int = 0
    state: str = ""
    url: str = ""
    label: str = ""


def _months(today, count=MONTHS):
    """The first days of the last `count` months, oldest first."""
    year, month = today.year, today.month
    firsts = []
    for _ in range(count):
        firsts.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(firsts))


def month_key(day):
    return f"{day.year}-{day.month:02d}"


def month_label(day):
    return f"{date_format(day, 'F').lower()} {day.year}"


def _waiting(request_obj):
    return request_obj.closed_at is None and request_obj.delivered_items < (
        request_obj.total_items
    )


def _sum_up(cell, now):
    waiting = [r for r in cell.requests if _waiting(r)]
    cell.total = sum(r.total_items for r in cell.requests)
    cell.delivered = sum(r.delivered_items for r in cell.requests)
    cell.missing = sum(r.total_items - r.delivered_items for r in waiting)
    cell.to_review = sum(r.to_review for r in cell.requests)
    if cell.total and cell.delivered == cell.total:
        cell.state = KOMPLET
    elif not waiting:
        cell.state = ZAMKNIETA
    elif any(r.deadline and r.deadline < now for r in waiting):
        cell.state = PO_TERMINIE
    elif not any(r.delivered_items for r in waiting):
        cell.state = NIC
    else:
        cell.state = BRAKUJE
    # One request to look at: straight there; several: the client's card.
    target = waiting or cell.requests
    cell.url = (
        reverse("requests:detail", args=[target[0].pk])
        if len(target) == 1
        else reverse("clients:detail", args=[target[0].client_id])
    )


def requests_in(owner, start, end=None):
    """The owner's requests for documents sent from `start` (to `end`)."""
    queryset = Request.objects.filter(
        created_by=owner, awaiting_confirmation=False, created_at__gte=start
    )
    if end is not None:
        queryset = queryset.filter(created_at__lt=end)
    return with_stats(queryset.exclude(items__kind=RequestItemKind.QUESTION)).annotate(
        to_review=Count(
            "items",
            filter=Q(items__status=RequestItemStatus.DOSTARCZONY)
            | Q(
                items__status=RequestItemStatus.NIE_DOTYCZY,
                items__not_applicable_accepted=False,
            ),
            distinct=True,
        )
    )


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def build(owner, selected=None, query="", only_missing=False, today=None):
    """The table, newest month on the right, and the chosen month's summary."""
    now = timezone.now()
    today = today or timezone.localdate()
    months = _months(today)
    keys = [month_key(m) for m in months]

    rows = {}
    requests = requests_in(owner, _aware(months[0])).select_related("client")
    for request_obj in requests:
        sent = timezone.localtime(request_obj.created_at).date()
        key = month_key(sent)
        if key not in keys:
            continue
        row = rows.setdefault(
            request_obj.client_id,
            {
                "client": request_obj.client,
                "cells": {
                    k: Cell(label=month_label(m))
                    for k, m in zip(keys, months, strict=True)
                },
            },
        )
        row["cells"][key].requests.append(request_obj)
    for row in rows.values():
        for cell in row["cells"].values():
            if cell.requests:
                _sum_up(cell, now)

    has_requests = [
        k for k in keys if any(r["cells"][k].requests for r in rows.values())
    ]
    if selected not in keys:
        selected = has_requests[-1] if has_requests else keys[-1]

    states = [r["cells"][selected].state for r in rows.values()]
    summary = {
        "label": month_label(months[keys.index(selected)]),
        "clients": sum(1 for s in states if s),
        "complete": states.count(KOMPLET),
        "waiting": sum(1 for s in states if s in OPEN_STATES),
        "overdue": states.count(PO_TERMINIE),
        "to_review": sum(r["cells"][selected].to_review for r in rows.values()),
        "remindable": sum(
            1
            for r in rows.values()
            for request_obj in r["cells"][selected].requests
            if _waiting(request_obj)
        ),
    }

    shown = sorted(rows.values(), key=lambda r: r["client"].name.lower())
    if query:
        needle = query.lower()
        shown = [r for r in shown if needle in r["client"].name.lower()]
    if only_missing:
        shown = [r for r in shown if r["cells"][selected].state in OPEN_STATES]
    for row in shown:
        row["cells"] = [row["cells"][k] for k in keys]

    return {
        "months": [
            {"key": k, "label": month_label(m), "short": date_format(m, "M").lower()}
            for k, m in zip(keys, months, strict=True)
        ],
        "selected": selected,
        "selected_index": keys.index(selected),
        "rows": shown,
        "summary": summary,
        "has_requests": bool(rows),
    }


def waiting_in(owner, selected):
    """The requests of a month still waiting on the client - for "Przypomnij
    wszystkim"."""
    year, month = (int(part) for part in selected.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return [
        request_obj
        for request_obj in requests_in(
            owner, _aware(start), _aware(end)
        ).select_related("client", "created_by")
        if _waiting(request_obj)
    ]
