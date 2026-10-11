#!/usr/bin/env bash
# Once a week (cron): rkhunter looks for rootkits and replaced system
# programs. Only its warnings are kept; any warning is an alarm. It does
# raise false alarms after system updates - `sudo rkhunter --propupd` records
# the updated programs as the new normal once you have checked them.

# shellcheck disable=SC1091
. /usr/local/lib/monituj-security/lib.sh || exit 1
command -v rkhunter >/dev/null 2>&1 || exit 0
mkdir -p "$STATE_DIR"
rkhunter --update --nocolors >/dev/null 2>&1
rkhunter --check --skip-keypress --report-warnings-only --nocolors \
  >"$STATE_DIR/rkhunter.last" 2>&1
if [ -s "$STATE_DIR/rkhunter.last" ]; then
  head -n 80 "$STATE_DIR/rkhunter.last" \
    | monituj_alert "serwer: rkhunter zgłasza ostrzeżenia" "rkhunter:$(date +%F)"
fi
