"""The calendar feed (.ics) a phone or Google / Outlook subscribes to by a
secret link: the person's reminders and the deadlines and recurring sends
of every account they work in. Whole-day events, refreshed by the calendar
app every few hours."""

from datetime import timedelta

from django.utils import timezone

from apps.accounts import team
from apps.agenda import calendar

PAST_DAYS = 30
FUTURE_DAYS = 180
LINE = 75


def accounts_of(user):
    """The user's own account and the teams they may work in now."""
    found = [user]
    for membership in user.memberships.select_related("owner"):
        if team.has_access(membership):
            found.append(membership.owner)
    return found


def _escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _fold(line):
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= LINE:
        return line
    parts, current = [], b""
    for char in line:
        piece = char.encode("utf-8")
        if len(current) + len(piece) > (LINE if not parts else LINE - 1):
            parts.append(current.decode("utf-8"))
            current = b""
        current += piece
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _slug(path):
    """'/prosby/423/' -> 'przypomnienia-423'. The panel's old prefix is kept,
    so calendars that already subscribed see the same events, not new ones."""
    parts = [part for part in path.split("/") if part]
    if parts and parts[0] in ("prosby", "pytania"):
        parts[0] = "przypomnienia"
    return "-".join(parts)


def feed_for(user, site_url):
    today = timezone.localdate()
    start, end = today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS)
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Monituj//Kalendarz//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Monituj",
        "X-PUBLISHED-TTL:PT3H",
    ]
    for account in accounts_of(user):
        events = [
            *calendar.reminders(account, start, end),
            *calendar.deadlines(account, start, end),
            *calendar.sends(account, start, end),
        ]
        for day, event in events:
            if event["kind"] == "mine" and event.get("done"):
                continue
            title = event["label"]
            if event.get("client"):
                title += f" ({event['client']})"
            key = event.get("reminder")
            # Stable across refreshes - a phone matches events by UID.
            uid = (
                f"reminder-{key.pk}@monituj"
                if key is not None
                else f"{event['kind']}-{day:%Y%m%d}-{_slug(event['url'])}@monituj"
            )
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_escape(title)}",
            ]
            if event.get("url"):
                lines.append(f"URL:{site_url.rstrip('/')}{event['url']}")
            lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
