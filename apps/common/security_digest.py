"""The daily security report to settings.SECURITY_EMAIL: what happened on
the site in the last day, what needs a look, the server's own report
(deploy/security/daily-report.sh hands it in) and the day's security log as
a CSV attachment - a copy of the trail kept outside the server, where
someone who broke in can't erase it.

It goes out every day, quiet or not: a morning without it is a signal too.
The server's cron sends it at 7:00; if that didn't happen, the worker sends
the site's part at 9:30 and says the server's is missing (tasks.py).
"""

import csv
import io
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditLog
from apps.common import throttle

PERIOD = timedelta(hours=24)
SENT_KEY = "security-digest-sent"
# The fallback stays quiet if a report went out this recently.
SENT_WINDOW = timedelta(hours=20)

# Thresholds for "needs a look".
MANY_FAILED_FROM_ONE_IP = 20
MANY_FAILED_ADMIN = 3
MANY_DOWNLOADS = 100
MANY_DELETED_REQUESTS = 50
MANY_REGISTRATIONS = 50

# The trail worth keeping off the server (the CSV attachment).
LOGGED = [
    AuditEvent.USER_REGISTERED,
    AuditEvent.USER_LOGIN,
    AuditEvent.USER_LOGIN_FAILED,
    AuditEvent.USER_LOGOUT,
    AuditEvent.PASSWORD_CHANGED,
    AuditEvent.PASSWORD_CHANGE_REQUESTED,
    AuditEvent.EMAIL_CHANGE_REQUESTED,
    AuditEvent.EMAIL_CHANGED,
    AuditEvent.ACCOUNT_DELETION_REQUESTED,
    AuditEvent.GOOGLE_LINKED,
    AuditEvent.GOOGLE_UNLINKED,
    AuditEvent.TWO_FACTOR_ENABLED,
    AuditEvent.TWO_FACTOR_DISABLED,
    AuditEvent.TWO_FACTOR_FAILED,
    AuditEvent.BACKUP_CODES_REGENERATED,
    AuditEvent.PASSWORD_ACCESS_FAILED,
    AuditEvent.TEAM_INVITED,
    AuditEvent.TEAM_JOINED,
    AuditEvent.TEAM_MEMBER_REMOVED,
    AuditEvent.CLIENTS_IMPORTED,
    AuditEvent.CLIENT_DELETED,
    AuditEvent.REQUEST_DELETED,
    AuditEvent.PLAN_CHANGED,
]
MAX_LOG_ROWS = 20000
# Marks a line of the server's report that needs a look (daily-report.sh).
HOST_WARNING = "!"


def _count(entries, event):
    return sum(1 for e in entries if e.event == event)


def _top(counter, limit=5):
    return ", ".join(f"{key} ({n})" for key, n in counter.most_common(limit)) or "-"


def _local(moment):
    return timezone.localtime(moment).strftime("%d.%m %H:%M")


def build(now=None, host_report=""):
    """-> (subject, body, attachments)."""
    now = now or timezone.now()
    since = now - PERIOD
    user_model = get_user_model()
    entries = list(
        AuditLog.objects.filter(created_at__gte=since, created_at__lt=now)
        .select_related("actor")
        .order_by("created_at")
    )
    attention = []

    # --- sign-ins
    logins = [e for e in entries if e.event == AuditEvent.USER_LOGIN]
    failed = [e for e in entries if e.event == AuditEvent.USER_LOGIN_FAILED]
    failed_admin = [e for e in failed if (e.metadata or {}).get("admin")]
    failed_by_ip = Counter(e.ip_address or "brak adresu" for e in failed)
    staff_logins = [e for e in logins if e.actor is not None and e.actor.is_staff]
    for ip, n in failed_by_ip.most_common(3):
        if n >= MANY_FAILED_FROM_ONE_IP:
            attention.append(f"{n} nieudanych logowań z jednego adresu: {ip}")
    if len(failed_admin) >= MANY_FAILED_ADMIN:
        attention.append(
            f"{len(failed_admin)} nieudanych prób logowania do panelu administratora"
        )
    for entry in staff_logins:
        attention.append(
            f"logowanie administratora {entry.actor.email} "
            f"o {_local(entry.created_at)} z adresu {entry.ip_address or 'brak'} "
            "- jeśli to nie Ty, to włamanie"
        )

    # --- administrators
    staff = list(
        user_model.objects.filter(is_staff=True)
        .order_by("email")
        .values_list("email", "is_superuser", "date_joined")
    )
    for email, _superuser, joined in staff:
        if joined >= since:
            attention.append(f"nowe konto z uprawnieniami administratora: {email}")
    admin_actions = list(
        LogEntry.objects.filter(action_time__gte=since, action_time__lt=now)
        .select_related("user")
        .order_by("action_time")
    )
    for entry in entries:
        if (
            entry.event == AuditEvent.TWO_FACTOR_DISABLED
            and entry.actor is not None
            and entry.actor.is_staff
        ):
            attention.append(
                f"wyłączono weryfikację dwuetapową administratora {entry.actor.email}"
            )

    # --- accounts and files
    registrations = _count(entries, AuditEvent.USER_REGISTERED)
    if registrations >= MANY_REGISTRATIONS:
        attention.append(f"{registrations} nowych rejestracji w ciągu doby")
    downloads = Counter(
        e.actor_id
        for e in entries
        if e.event == AuditEvent.FILE_DOWNLOAD and e.actor_id
    )
    for account, n in downloads.most_common(3):
        if n >= MANY_DOWNLOADS:
            attention.append(f"konto #{account} pobrało {n} plików w ciągu doby")
    deleted = Counter(
        e.actor_id
        for e in entries
        if e.event == AuditEvent.REQUEST_DELETED and e.actor_id
    )
    for account, n in deleted.most_common(3):
        if n >= MANY_DELETED_REQUESTS:
            attention.append(f"konto #{account} usunęło {n} próśb w ciągu doby")

    # --- the canary
    canary = (settings.SECURITY_CANARY_EMAIL or "").strip().lower()
    canary_hits = [
        e
        for e in failed
        if canary and (e.metadata or {}).get("email", "").strip().lower() == canary
    ]
    if canary_hits:
        attention.append(
            f"adres-przynęta z bazy danych użyty {len(canary_hits)} raz(y) - "
            "możliwy wyciek bazy"
        )

    # --- the server
    host_report = (host_report or "").strip()
    host_warnings = [
        line.lstrip(HOST_WARNING).strip()
        for line in host_report.splitlines()
        if line.startswith(HOST_WARNING)
    ]
    attention += [f"serwer: {line}" for line in host_warnings]
    if not host_report:
        attention.append(
            "raport z serwera nie dotarł - sprawdź, czy działa cron "
            "(README, „Monitoring bezpieczeństwa”)"
        )

    lines = [
        f"Raport bezpieczeństwa Monituj - {timezone.localtime(now):%d.%m.%Y %H:%M}",
        f"Okres: ostatnie 24 godziny (od {_local(since)}).",
        "",
        "WYMAGA UWAGI",
        *([f"- {item}" for item in attention] or ["- nic"]),
        "",
        "LOGOWANIA",
        f"- udane: {len(logins)}",
        f"- nieudane: {len(failed)}"
        + (f" (panel administratora: {len(failed_admin)})" if failed_admin else ""),
        f"- adresy z największą liczbą nieudanych prób: {_top(failed_by_ip)}",
        "- błędne kody weryfikacji dwuetapowej: "
        f"{_count(entries, AuditEvent.TWO_FACTOR_FAILED)}",
        "- błędne hasła do próśb chronionych hasłem: "
        f"{_count(entries, AuditEvent.PASSWORD_ACCESS_FAILED)}",
        "",
        "ADMINISTRATORZY",
        "- konta z dostępem do panelu: "
        + (
            ", ".join(
                email + (" (superużytkownik)" if superuser else "")
                for email, superuser, _ in staff
            )
            or "brak"
        ),
        f"- logowania administratorów: {len(staff_logins)}",
        *[
            f"  {_local(e.created_at)}  {e.actor.email}  {e.ip_address or 'brak'}"
            for e in staff_logins
        ],
        f"- działania w panelu administratora: {len(admin_actions)}",
        *[
            f"  {_local(a.action_time)}  {a.user.email}  "
            f"{a.get_action_flag_display()}: {a.object_repr[:80]}"
            for a in admin_actions[:50]
        ],
        "",
        "KONTA",
        f"- nowe rejestracje: {registrations}",
        f"- usunięcia kont: {_count(entries, AuditEvent.ACCOUNT_DELETION_REQUESTED)}",
        f"- zmiany hasła: {_count(entries, AuditEvent.PASSWORD_CHANGED)}",
        "- prośby o reset albo zmianę hasła: "
        f"{_count(entries, AuditEvent.PASSWORD_CHANGE_REQUESTED)}",
        f"- zmiany adresu e-mail: {_count(entries, AuditEvent.EMAIL_CHANGED)}",
        "- wyłączenia weryfikacji dwuetapowej: "
        f"{_count(entries, AuditEvent.TWO_FACTOR_DISABLED)}",
        "",
        "DOKUMENTY I PROŚBY",
        f"- przesłane pliki: {_count(entries, AuditEvent.DOCUMENT_UPLOADED)}",
        f"- pobrania plików: {_count(entries, AuditEvent.FILE_DOWNLOAD)}"
        + (
            "; najwięcej: "
            + _top(Counter({f"konto #{k}": v for k, v in downloads.items()}), 3)
            if downloads
            else ""
        ),
        f"- usunięte prośby: {_count(entries, AuditEvent.REQUEST_DELETED)}",
        f"- importy klientów: {_count(entries, AuditEvent.CLIENTS_IMPORTED)}",
        "",
        "PRZYNĘTA W BAZIE (kanarek)",
        (
            f"- ustawiona; próby użycia w tym okresie: {len(canary_hits)}"
            if canary
            else "- nie ustawiona (SECURITY_CANARY_EMAIL, `manage.py security_canary`)"
        ),
        "",
        "SERWER",
        host_report or "(brak raportu z serwera)",
        "",
        "W załączniku: dziennik zdarzeń bezpieczeństwa z tego okresu (CSV). "
        "Zachowaj te wiadomości - to kopia śladów poza serwerem.",
    ]
    subject = (
        f"{settings.EMAIL_SUBJECT_PREFIX}Raport bezpieczeństwa "
        f"{timezone.localtime(now):%d.%m.%Y}: "
        + (f"do sprawdzenia ({len(attention)})" if attention else "spokojnie")
    )
    name = f"monituj-dziennik-{timezone.localtime(now):%Y-%m-%d}.csv"
    return subject, "\n".join(lines), [(name, _log_csv(entries), "text/csv")]


def _log_csv(entries):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["czas", "zdarzenie", "konto_id", "konto", "ip", "przegladarka", "dane"]
    )
    wanted = set(LOGGED)
    rows = [e for e in entries if e.event in wanted][-MAX_LOG_ROWS:]
    for entry in rows:
        metadata = entry.metadata or {}
        writer.writerow(
            [
                timezone.localtime(entry.created_at).isoformat(timespec="seconds"),
                entry.event,
                entry.actor_id or "",
                entry.actor.email if entry.actor is not None else "",
                entry.ip_address or "",
                entry.user_agent,
                "; ".join(f"{k}={v}" for k, v in metadata.items())[:300],
            ]
        )
    return out.getvalue()


def send(now=None, host_report=""):
    subject, body, attachments = build(now=now, host_report=host_report)
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.SECURITY_EMAIL],
    )
    for name, content, mimetype in attachments:
        message.attach(name, content, mimetype)
    message.send(fail_silently=False)
    throttle.record(SENT_KEY)
    return subject


def sent_recently():
    return throttle.is_limited(SENT_KEY, 1, SENT_WINDOW)
