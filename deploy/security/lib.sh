#!/usr/bin/env bash
# Shared by the security scripts (README, "Monitoring bezpieczeństwa").
# Alarms and the daily report leave through the site's own mailer, so the
# server needs no mail setup of its own:
#   docker compose exec web python manage.py security_alert / security_digest
# Everything is also written to $LOG - if the site is down, the trail stays.

CONF=/etc/monituj-security.conf
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
APP_DIR="${APP_DIR:-/srv/monituj}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
STATE_DIR="${STATE_DIR:-/var/lib/monituj-security}"
LOG="${LOG:-/var/log/monituj-security.log}"
export COMPOSE_FILE

compose() { (cd "$APP_DIR" && timeout 120 docker compose "$@"); }

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

# monituj_alert "subject" ["key"]  - details on standard input.
monituj_alert() {
  local subject="$1" key="${2:-$1}" details
  details="$(cat)"
  log "ALARM: $subject"
  printf '%s\n' "$details" >>"$LOG"
  if ! printf '%s\n' "$details" | compose exec -T web \
      python manage.py security_alert "$subject" --key "$key" >>"$LOG" 2>&1; then
    log "NIE WYSŁANO (strona nie działa?): $subject"
    return 1
  fi
}
