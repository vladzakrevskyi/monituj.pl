#!/usr/bin/env bash
# Every morning (cron, 7:00): the server's part of the daily security report -
# who logged in over SSH, what ran with sudo, what fail2ban blocked, whether
# anything connected to the database from outside the site, disk, containers,
# updates. Handed to the site, which adds its own part and emails the whole
# (manage.py security_digest). Lines starting with "!" need a look - the
# report lists them at the top.

# shellcheck disable=SC1091
. /usr/local/lib/monituj-security/lib.sh || exit 1
SINCE="24 hours ago"
REPORT="$(mktemp)"
trap 'rm -f "$REPORT"' EXIT
say() { printf '%s\n' "$*" >>"$REPORT"; }

say "Serwer: $(hostname), $(uptime -p 2>/dev/null || uptime)"

# --- SSH
ssh_log="$(journalctl --since "$SINCE" -t sshd -t sshd-session --no-pager -o short-iso 2>/dev/null)"
accepted="$(printf '%s\n' "$ssh_log" | grep -E 'Accepted (publickey|password|keyboard)' || true)"
failed_count="$(printf '%s\n' "$ssh_log" | grep -cE 'Failed password|Invalid user|authentication failure' || true)"
say ""
say "SSH - udane logowania: $(printf '%s' "$accepted" | grep -c . || true)"
if [ -n "$accepted" ]; then
  printf '%s\n' "$accepted" | sed -E 's/^([^ ]+) [^ ]+ [^:]+: Accepted ([a-z]+) for ([^ ]+) from ([^ ]+).*/  \1  \3 z \4 (\2)/' | tail -n 40 >>"$REPORT"
  if printf '%s\n' "$accepted" | grep -q 'Accepted password'; then
    say "! logowanie SSH hasłem - miały działać tylko klucze (sshd_config: PasswordAuthentication no)"
  fi
  if printf '%s\n' "$accepted" | grep -q ' for root '; then
    say "! logowanie SSH na konto root"
  fi
fi
say "SSH - nieudane próby: $failed_count"
printf '%s\n' "$ssh_log" | grep -oE 'from [0-9a-fA-F:.]+' | sort | uniq -c | sort -rn | head -n 5 \
  | awk '{print "  " $3 " (" $1 ")"}' >>"$REPORT"

# --- sudo
sudo_log="$(journalctl --since "$SINCE" -t sudo --no-pager -o short-iso 2>/dev/null | grep 'COMMAND=' || true)"
say ""
say "sudo - polecenia: $(printf '%s' "$sudo_log" | grep -c . || true)"
printf '%s\n' "$sudo_log" | sed -E 's/^([^ ]+) [^ ]+ sudo[^:]*: +([^ ]+) :.*COMMAND=(.*)$/  \1  \2: \3/' \
  | grep -v 'monituj-security' | cut -c1-200 | tail -n 30 >>"$REPORT"

# --- fail2ban
if command -v fail2ban-client >/dev/null 2>&1; then
  status="$(fail2ban-client status sshd 2>/dev/null)"
  say ""
  say "fail2ban (sshd): zablokowane teraz: $(printf '%s\n' "$status" | awk -F: '/Currently banned/ {gsub(/[ \t]/,"",$2); print $2}'), łącznie: $(printf '%s\n' "$status" | awk -F: '/Total banned/ {gsub(/[ \t]/,"",$2); print $2}')"
else
  say ""
  say "! fail2ban nie jest zainstalowany"
fi

# --- the database: connections that didn't come from the site's containers.
# The site connects over the Docker network; a connection from inside the
# database container ([local]) or from the host (the network's gateway) is
# someone at the server's console.
gateway="$(compose ps -q db 2>/dev/null | xargs -r docker inspect -f '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' 2>/dev/null)"
db_log="$(compose logs --since 24h --no-log-prefix db 2>/dev/null | grep 'connection authorized' || true)"
outside="$(printf '%s\n' "$db_log" | grep -E "host=\[local\]|host=${gateway:-none} " || true)"
say ""
say "Baza danych - połączenia aplikacji: $(printf '%s' "$db_log" | grep -c . || true)"
if [ -n "$outside" ]; then
  say "! połączenia z bazą spoza aplikacji: $(printf '%s\n' "$outside" | grep -c .) (konsola serwera - jeśli to nie Ty, ktoś czytał bazę)"
  printf '%s\n' "$outside" | cut -c1-160 | tail -n 10 | sed 's/^/  /' >>"$REPORT"
elif [ -z "$db_log" ]; then
  say "! brak wpisów o połączeniach z bazą - czy baza loguje połączenia (docker-compose.prod.yml: log_connections)?"
fi

# --- containers, code, disk, updates
say ""
say "Kontenery:"
compose ps --format '  {{.Service}}: {{.Status}}' 2>/dev/null >>"$REPORT"
for service in db redis web worker beat; do
  compose ps --status running --services 2>/dev/null | grep -qx "$service" \
    || say "! kontener $service nie działa"
done
say "Kod: $(git -C "$APP_DIR" log -1 --format='%h %s (%cd)' --date=short 2>/dev/null)"
[ -z "$(git -C "$APP_DIR" status --porcelain --untracked-files=no 2>/dev/null)" ] \
  || say "! kod strony różni się od repozytorium"
disk="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
say "Dysk: zajęte ${disk}%"
[ "${disk:-0}" -lt 85 ] || say "! kończy się miejsce na dysku (${disk}%)"
if [ -x /usr/lib/update-notifier/apt-check ]; then
  updates="$(/usr/lib/update-notifier/apt-check 2>&1 | cut -d';' -f2)"
  say "Zaległe aktualizacje bezpieczeństwa: ${updates:-?}"
  [ "${updates:-0}" -lt 20 ] 2>/dev/null || say "! dużo zaległych aktualizacji bezpieczeństwa (${updates}) - czy działa unattended-upgrades?"
fi
[ -f /var/run/reboot-required ] && say "Serwer czeka na restart po aktualizacji."

# --- what the watch and the weekly rootkit check found
say ""
say "Alarmy z serwera (24 h): $(awk -v since="$(date -d "$SINCE" '+%F %T')" '$0 >= since && / ALARM: /' "$LOG" 2>/dev/null | grep -c . || true)"
awk -v since="$(date -d "$SINCE" '+%F %T')" '$0 >= since && / ALARM: /' "$LOG" 2>/dev/null | tail -n 20 | sed 's/^/  /' >>"$REPORT"
if [ -s "$STATE_DIR/rkhunter.last" ]; then
  say "! rkhunter (kontrola rootkitów) ma ostrzeżenia z $(date -r "$STATE_DIR/rkhunter.last" '+%F') - zob. $STATE_DIR/rkhunter.last"
elif [ -f "$STATE_DIR/rkhunter.last" ]; then
  say "rkhunter: ostatnia kontrola $(date -r "$STATE_DIR/rkhunter.last" '+%F') bez ostrzeżeń"
fi

if compose exec -T web python manage.py security_digest --host-report - <"$REPORT" >>"$LOG" 2>&1; then
  log "raport dzienny wysłany"
else
  log "RAPORT DZIENNY NIE WYSŁANY (strona nie działa?)"
  cat "$REPORT" >>"$LOG"
fi
