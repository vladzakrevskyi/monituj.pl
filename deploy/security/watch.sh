#!/usr/bin/env bash
# Every 10 minutes (cron): did anything change that only a break-in - or you -
# would change? System accounts and sudo, SSH keys and settings, cron jobs,
# the site's .env, nginx, these scripts; the ports the server listens on; the
# containers that run; the site's code (it must match git).
# An alarm goes out once per change; the new state becomes the baseline.
# The first run only records the baseline.   --accept: record it, no alarm.

# shellcheck disable=SC1091
. /usr/local/lib/monituj-security/lib.sh || exit 1
mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
# Not in the middle of a deploy (deploy.sh holds this lock): containers
# stop and start then. Opened for reading only: the file belongs to the
# deploy user, and Linux (fs.protected_regular) refuses even root a write
# to someone else's file in /tmp. No file - no deploy has run since boot.
DEPLOY_LOCK=/tmp/monituj-deploy.lock
if [ -r "$DEPLOY_LOCK" ] && { exec 9<"$DEPLOY_LOCK"; } 2>/dev/null; then
  flock -n 9 || exit 0
fi
ACCEPT=0
[ "${1:-}" = "--accept" ] && ACCEPT=1

# What changed between the stored state and the current one -> an alarm.
check() {  # name, title, current-state-file
  local name="$1" title="$2" current="$3" stored="$STATE_DIR/$1"
  if [ ! -f "$stored" ] || [ "$ACCEPT" = 1 ]; then
    cp "$current" "$stored"
    return
  fi
  if ! cmp -s "$current" "$stored"; then
    {
      echo "$title"
      echo
      echo "Zmiany (< było, > jest):"
      diff "$stored" "$current" | grep -E '^[<>]' | head -n 60
    } | monituj_alert "serwer: $title" "watch:$name:$(sha256sum <"$current" | cut -c1-16)"
    cp "$current" "$stored"
  fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 1. Files: a checksum each, never their content.
FILES=(
  /etc/passwd /etc/group /etc/shadow /etc/sudoers /etc/sudoers.d/*
  /etc/ssh/sshd_config /etc/ssh/sshd_config.d/* /etc/pam.d/sshd
  /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys
  /etc/crontab /etc/cron.d/* /var/spool/cron/crontabs/*
  /etc/nginx/nginx.conf /etc/nginx/sites-enabled/*
  "$APP_DIR/.env" /etc/monituj-security.conf
  /usr/local/lib/monituj-security/* /usr/local/sbin/monituj-security-*
)
for file in "${FILES[@]}"; do
  [ -f "$file" ] && printf '%s  %s\n' "$(sha256sum <"$file" | cut -d' ' -f1)" "$file"
done | sort -k2 >"$TMP/files"
check files "zmieniono pliki systemowe albo konfigurację" "$TMP/files"

# 2. Ports the server listens on.
ss -H -tln 2>/dev/null | awk '{print $4}' | sort -u >"$TMP/ports"
check ports "zmieniły się porty, na których serwer nasłuchuje" "$TMP/ports"

# 3. Running containers (image and name).
docker ps --format '{{.Image}}  {{.Names}}' 2>/dev/null | sort >"$TMP/containers"
check containers "zmieniła się lista działających kontenerów" "$TMP/containers"

# 4. The site's code must be exactly what git has.
git -C "$APP_DIR" status --porcelain --untracked-files=no 2>/dev/null >"$TMP/code"
check code "kod strony na serwerze różni się od repozytorium" "$TMP/code"
