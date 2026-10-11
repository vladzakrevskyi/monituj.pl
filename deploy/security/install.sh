#!/usr/bin/env bash
# Sets up the server's side of the security monitoring - once, and again
# after these scripts change (README, "Monitoring bezpieczeństwa"):
#
#   sudo /srv/monituj/deploy/security/install.sh
#
# - an alarm on every SSH login (PAM),
# - a watch on system files, ports, containers and the site's code (10 min),
# - the daily security report at 7:00,
# - a weekly rootkit check (rkhunter).
# Safe to run again. --test sends a test alarm at the end.

set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo "Uruchom przez sudo." >&2; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/../.." && pwd)"
LIB=/usr/local/lib/monituj-security

echo "1. Skrypty -> $LIB"
install -d -m 755 "$LIB"
install -m 644 "$HERE/lib.sh" "$LIB/lib.sh"
install -m 755 "$HERE/ssh-login-alert.sh" "$LIB/ssh-login-alert.sh"
install -m 755 "$HERE/watch.sh" /usr/local/sbin/monituj-security-watch
install -m 755 "$HERE/daily-report.sh" /usr/local/sbin/monituj-security-report
install -m 755 "$HERE/weekly-rootkit.sh" /usr/local/sbin/monituj-security-rootkit
cat >/etc/monituj-security.conf <<CONF
# Written by deploy/security/install.sh.
APP_DIR=$APP_DIR
COMPOSE_FILE=docker-compose.prod.yml
CONF
install -d -m 700 /var/lib/monituj-security
touch /var/log/monituj-security.log && chmod 600 /var/log/monituj-security.log

echo "2. Alarm przy logowaniu SSH (PAM)"
PAM_LINE="session optional pam_exec.so seteuid $LIB/ssh-login-alert.sh"
grep -qF "$LIB/ssh-login-alert.sh" /etc/pam.d/sshd || echo "$PAM_LINE" >>/etc/pam.d/sshd

echo "3. Harmonogram (cron)"
cat >/etc/cron.d/monituj-security <<'CRON'
# Monituj - monitoring bezpieczeństwa (deploy/security/install.sh).
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/10 * * * * root /usr/local/sbin/monituj-security-watch >/dev/null 2>&1
0 7 * * *    root /usr/local/sbin/monituj-security-report >/dev/null 2>&1
30 4 * * 0   root /usr/local/sbin/monituj-security-rootkit >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/monituj-security
cat >/etc/logrotate.d/monituj-security <<'ROTATE'
/var/log/monituj-security.log {
    monthly
    rotate 12
    compress
    missingok
    notifempty
    create 600 root root
}
ROTATE

echo "4. Kontrola rootkitów (rkhunter)"
if ! command -v rkhunter >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rkhunter >/dev/null
fi
rkhunter --propupd --nocolors >/dev/null 2>&1 || true

echo "5. Stan wyjściowy plików, portów i kontenerów"
/usr/local/sbin/monituj-security-watch --accept
for state in files ports containers code; do
  [ -f "/var/lib/monituj-security/$state" ] || {
    echo "Nie udało się zapisać stanu wyjściowego ($state) - kontrola co 10 minut nie zadziała." >&2
    echo "Zobacz: sudo bash -x /usr/local/sbin/monituj-security-watch --accept" >&2
    exit 1
  }
done

echo
echo "Gotowe. Od teraz:"
echo "  - każde logowanie SSH = wiadomość na adres z SECURITY_EMAIL,"
echo "  - zmiana pliku systemowego, portu, kontenera albo kodu = wiadomość (do 10 minut),"
echo "  - codziennie o 7:00 raport bezpieczeństwa z dziennikiem w załączniku."
echo "Dziennik na serwerze: /var/log/monituj-security.log"
if [ "${1:-}" = "--test" ]; then
  # shellcheck disable=SC1091
  . "$LIB/lib.sh"
  # Straight through the site, so its answer shows here: "wysłano", or why not.
  if answer="$(echo "To tylko próba - instalacja monitoringu na $(hostname)." \
      | compose exec -T web python manage.py security_alert \
          "próba alarmu z serwera" --key "test:$(date +%s)" 2>&1)" \
      && printf '%s' "$answer" | grep -q "wysłano"; then
    echo "Wysłano próbny alarm - sprawdź skrzynkę."
  else
    echo "Próbny alarm NIE został wysłany:" >&2
    printf '%s\n' "$answer" | tail -n 5 >&2
    echo "Sprawdź: czy kontener web działa (docker compose ps), SECURITY_ALERTS i SECURITY_EMAIL w .env." >&2
    exit 1
  fi
fi
