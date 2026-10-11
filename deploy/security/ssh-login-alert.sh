#!/usr/bin/env bash
# An alarm for every SSH login: who, from where. Called by PAM
# (/etc/pam.d/sshd: session optional pam_exec.so seteuid <this script>).
# Never fails and never waits - a broken alarm must not lock anyone out.

[ "${PAM_TYPE:-}" = "open_session" ] || exit 0
# shellcheck disable=SC1091
. /usr/local/lib/monituj-security/lib.sh 2>/dev/null || exit 0

(
  {
    echo "Użytkownik: ${PAM_USER:-?}"
    echo "Z adresu: ${PAM_RHOST:-?}"
    echo "Serwer: $(hostname)"
    echo "Terminal: ${PAM_TTY:-?}"
  } | monituj_alert "logowanie SSH: ${PAM_USER:-?} z ${PAM_RHOST:-?}" \
        "ssh:${PAM_USER:-}:${PAM_RHOST:-}"
) </dev/null >/dev/null 2>&1 &
exit 0
