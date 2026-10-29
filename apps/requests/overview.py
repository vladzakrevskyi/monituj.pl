"""Zestawienie miesięczne: who sent everything and who still owes something,
client by client, for a chosen month.

A month here is the month a request was sent in, so the view needs no
guessing from names. Every request gets exactly one state - overdue, waiting
for the client, waiting for the sender's check, complete or closed - and a
client the most urgent state of their requests that month, so the counts on
top never overlap: each client is counted once. A client with several
requests that month is one row that opens to show each of them. Questions
have their own list (Pytania) and stay out of it."""

from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.db.models import Count, Prefetch, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from apps.requests.models import (
    Request,
    RequestItem,
    RequestItemKind,
    RequestItemStatus,
)
from apps.requests.services import MISSING_STATUSES, _plural, with_stats

# Months of history shown next to each client, and how far back the month
# switcher goes.
HISTORY_MONTHS = 6
MONTHS_BACK = 12
# Missing documents named in a row before "+ N innych".
MISSING_SHOWN = 3

PO_TERMINIE = "po_terminie"
CZEKAMY = "czekamy"
DO_SPRAWDZENIA = "do_sprawdzenia"
KOMPLET = "komplet"
ZAMKNIETA = "zamknieta"
# Most urgent first: a client's state is the first one any request has.
URGENCY = [PO_TERMINIE, CZEKAMY, DO_SPRAWDZENIA, KOMPLET, ZAMKNIETA]
LABELS = {
    PO_TERMINIE: "Po terminie",
    CZEKAMY: "Czekamy na klienta",
    DO_SPRAWDZENIA: "Do sprawdzenia",
    KOMPLET: "Komplet",
    ZAMKNIETA: "Zamknięta",
}
# The filter tiles, in order; "" is everyone.
TILES = ["", KOMPLET, DO_SPRAWDZENIA, CZEKAMY, PO_TERMINIE]
# The client still owes something - what "Przypomnij" is for.
WAITING = {PO_TERMINIE, CZEKAMY}


def deadline_text(days):
    """ "3 dni temu", "dziś", "za 1 dzień" - or "" without a deadline."""
    if days is None:
        return ""
    if days == 0:
        return "dziś"
    count = abs(days)
    unit = "dzień" if count == 1 else "dni"
    return f"{count} {unit} temu" if days < 0 else f"za {count} {unit}"


@dataclass
class RequestLine:
    request: Request
    state: str
    missing: list
    url: str
    days_left: int | None = None

    @property
    def label(self):
        return LABELS[self.state]

    @property
    def deadline_text(self):
        return deadline_text(self.days_left) if self.state in WAITING else ""


@dataclass
class Row:
    client: object
    lines: list = field(default_factory=list)
    state: str = ""
    missing: list = field(default_factory=list)
    deadline: datetime | None = None
    to_review: int = 0
    history: list = field(default_factory=list)
    # Whole days to the most urgent deadline - negative once it's past.
    days_left: int | None = None

    @property
    def label(self):
        return LABELS[self.state]

    @property
    def waiting(self):
        return self.state in WAITING

    @property
    def missing_shown(self):
        return self.missing[:MISSING_SHOWN]

    @property
    def missing_more(self):
        return max(len(self.missing) - MISSING_SHOWN, 0)

    @property
    def url(self):
        """One request: straight to it; several open in the row."""
        return self.lines[0].url if len(self.lines) == 1 else ""

    @property
    def deadline_text(self):
        return deadline_text(self.days_left)

    @property
    def count_text(self):
        count = len(self.lines)
        return f"{count} {_plural(count, 'prośba', 'prośby', 'próśb')}"

    @property
    def review_url(self):
        """The first request with something to check."""
        found = [line for line in self.lines if line.request.to_review]
        return found[0].url if found else ""


def month_key(day):
    return f"{day.year}-{day.month:02d}"


def month_label(day):
    return f"{date_format(day, 'F').lower()} {day.year}"


def _first_days(last, count):
    """The first days of `count` months ending with `last`, oldest first."""
    year, month = last.year, last.month
    firsts = []
    for _ in range(count):
        firsts.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(firsts))


def _next_month(day):
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def requests_in(owner, start, end=None):
    """The owner's requests for documents sent from `start` (to `end`), with
    their counts and items."""
    queryset = Request.objects.filter(
        created_by=owner, awaiting_confirmation=False, created_at__gte=start
    )
    if end is not None:
        queryset = queryset.filter(created_at__lt=end)
    return (
        with_stats(queryset.exclude(items__kind=RequestItemKind.QUESTION))
        .annotate(
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
        .select_related("client")
        .prefetch_related(
            Prefetch("items", queryset=RequestItem.objects.order_by("id"))
        )
    )


def request_state(request_obj, now):
    complete = request_obj.delivered_items >= request_obj.total_items
    if not complete:
        if request_obj.closed_at is not None:
            return ZAMKNIETA
        if request_obj.deadline and request_obj.deadline < now:
            return PO_TERMINIE
        return CZEKAMY
    return DO_SPRAWDZENIA if request_obj.to_review else KOMPLET


def most_urgent(states):
    return min(states, key=URGENCY.index) if states else ""


def _line(request_obj, now):
    state = request_state(request_obj, now)
    missing = (
        [i.name for i in request_obj.items.all() if i.status in MISSING_STATUSES]
        if state in WAITING
        else []
    )
    return RequestLine(
        request=request_obj,
        state=state,
        missing=missing,
        url=reverse("requests:detail", args=[request_obj.pk]),
    )


def _row(client, lines):
    # Most urgent first - the missing documents are named in that order too.
    lines = sorted(lines, key=lambda line: URGENCY.index(line.state))
    row = Row(client=client, lines=lines)
    row.state = most_urgent([line.state for line in lines])
    seen = set()
    for line in lines:
        for name in line.missing:
            if name.lower() not in seen:
                seen.add(name.lower())
                row.missing.append(name)
    deadlines = [
        line.request.deadline
        for line in lines
        if line.state in WAITING and line.request.deadline
    ]
    row.deadline = min(deadlines) if deadlines else None
    row.to_review = sum(line.request.to_review for line in lines)
    return row


def days_left(deadline, today):
    """Whole days from today to the deadline - negative once it's past."""
    return (timezone.localtime(deadline).date() - today).days


def months_to_pick(today):
    return [month_key(day) for day in _first_days(today, MONTHS_BACK)]


def build(owner, selected=None, state="", query="", today=None):
    """The chosen month, client by client: rows, the counts of the tiles,
    the clients asked before but not this month, and each client's last
    months as dots."""
    now = timezone.now()
    today = today or timezone.localdate()
    pickable = _first_days(today, MONTHS_BACK)
    keys = [month_key(day) for day in pickable]
    history_days = pickable[-HISTORY_MONTHS:]
    history_keys = [month_key(day) for day in history_days]

    by_month = {}
    for request_obj in requests_in(owner, _aware(pickable[0])):
        key = month_key(timezone.localtime(request_obj.created_at).date())
        by_month.setdefault(key, {}).setdefault(request_obj.client_id, []).append(
            _line(request_obj, now)
        )

    if selected not in keys:
        sent = [k for k in keys if k in by_month]
        selected = keys[-1] if keys[-1] in by_month or not sent else sent[-1]
    selected_day = pickable[keys.index(selected)]

    clients = {}
    for month in by_month.values():
        for lines in month.values():
            clients.setdefault(lines[0].request.client_id, lines[0].request.client)

    rows = []
    for client_id, lines in by_month.get(selected, {}).items():
        row = _row(clients[client_id], lines)
        for key, day in zip(history_keys, history_days, strict=True):
            month_lines = by_month.get(key, {}).get(client_id, [])
            month_state = most_urgent([line.state for line in month_lines])
            row.history.append(
                {
                    "key": key,
                    "label": month_label(day),
                    "state": month_state,
                    "state_label": LABELS.get(month_state, "bez prośby").lower(),
                    "selected": key == selected,
                }
            )
        rows.append(row)

    counts = {tile: 0 for tile in TILES}
    for row in rows:
        counts[""] += 1
        if row.state in counts:
            counts[row.state] += 1

    shown = rows
    if state in LABELS:
        shown = [row for row in shown if row.state == state]
    if query:
        needle = query.lower()
        shown = [row for row in shown if needle in row.client.name.lower()]
    shown.sort(key=lambda row: (URGENCY.index(row.state), row.client.name.lower()))
    for row in shown:
        if row.deadline is not None:
            row.days_left = days_left(row.deadline, today)
        for line in row.lines:
            if line.request.deadline is not None:
                line.days_left = days_left(line.request.deadline, today)

    # Asked before (in the months shown), not this month: easy to forget.
    asked_this_month = set(by_month.get(selected, {}))
    not_asked = sorted(
        (
            client
            for client_id, client in clients.items()
            if client_id not in asked_this_month
            and any(client_id in by_month.get(k, {}) for k in history_keys)
        ),
        key=lambda client: client.name.lower(),
    )

    index = keys.index(selected)
    return {
        "selected": selected,
        "month_label": month_label(selected_day),
        "previous": keys[index - 1] if index > 0 else "",
        "next": keys[index + 1] if index + 1 < len(keys) else "",
        "rows": shown,
        "tiles": [
            {"state": tile, "label": LABELS.get(tile, "Wszyscy"), "count": counts[tile]}
            for tile in TILES
        ],
        "state": state if state in LABELS else "",
        "remindable": sum(1 for row in rows if row.waiting),
        "not_asked": not_asked,
        "has_requests": bool(by_month),
        "month_has_requests": bool(rows),
    }


def waiting_by_client(owner, selected, client_id=None):
    """{client: [requests still waiting on them]} for a month - what
    "Przypomnij" sends one email per client about."""
    year, month = (int(part) for part in selected.split("-"))
    start = date(year, month, 1)
    now = timezone.now()
    found = {}
    queryset = requests_in(owner, _aware(start), _aware(_next_month(start)))
    if client_id is not None:
        queryset = queryset.filter(client_id=client_id)
    for request_obj in queryset.select_related("created_by"):
        if request_state(request_obj, now) in WAITING:
            found.setdefault(request_obj.client, []).append(request_obj)
    return found
