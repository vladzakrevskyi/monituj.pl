#!/usr/bin/env bash
# Updates monituj.pl on the server to the latest main - one command:
#
#   /srv/monituj/deploy/deploy.sh                 # the usual
#   /srv/monituj/deploy/deploy.sh --skip-backup   # only when the dump fails
#   /srv/monituj/deploy/deploy.sh --update-images # also newer postgres/redis
#
# 1. database dump (kept LEGAL_BACKUP_DAYS days, as the Privacy policy says)
# 2. latest code from GitHub (fast-forward only - never a merge on the server)
# 3. new image, settings checked before anything is switched
# 4. migrations, then the new containers (web, worker, beat)
# 5. health check
# 6. post_deploy: Stripe products/portal/webhook, legal documents archive,
#    missed VAT invoices, and a report of what needs attention
#
# Stops at the first error and prints how to go back.

set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/srv/monituj-backups}"
HEALTH_URL="http://127.0.0.1:8000/api/health/"

SKIP_BACKUP=0
UPDATE_IMAGES=0
for arg in "$@"; do
  case "$arg" in
    --skip-backup) SKIP_BACKUP=1 ;;
    --update-images) UPDATE_IMAGES=1 ;;
    *) echo "Nieznana opcja: $arg" >&2; exit 2 ;;
  esac
done

cd "$APP_DIR"
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
env_value() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2- | tr -d '"' || true; }

PREVIOUS="$(git rev-parse --short HEAD)"
DUMP=""
on_error() {
  printf '\n\033[31mAktualizacja przerwana (linia %s).\033[0m\n' "$1"
  echo "Kod przed aktualizacją: $PREVIOUS. Powrót:"
  echo "  git checkout $PREVIOUS && docker compose up -d --build"
  if [ -n "$DUMP" ]; then
    echo "Jeśli migracje zdążyły zmienić bazę, przywróć też kopię:"
    echo "  gunzip -c $DUMP | docker compose exec -T db sh -c 'psql -q -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'"
  fi
  echo "Logi: docker compose logs --tail 100 web"
}
trap 'on_error $LINENO' ERR

# One deploy at a time.
exec 9>/tmp/monituj-deploy.lock
flock -n 9 || { echo "Inna aktualizacja już trwa." >&2; exit 1; }

echo "=========================================="
echo "    Aktualizacja monituj.pl ($(date '+%F %T'))"
echo "=========================================="

[ -f .env ] || { echo "Brak pliku .env w $APP_DIR" >&2; exit 1; }
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Na serwerze są lokalne zmiany w plikach z repozytorium:" >&2
  git status --short --untracked-files=no >&2
  echo "Zatwierdź je u siebie i wypchnij albo cofnij: git checkout -- <plik>" >&2
  exit 1
fi

step "1. Kopia bazy danych"
if [ "$SKIP_BACKUP" = 1 ]; then
  warn "Pominięta (--skip-backup)."
else
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  DUMP="$BACKUP_DIR/db-$(date +%Y%m%d-%H%M%S)-$PREVIOUS.sql.gz"
  docker compose up -d db >/dev/null
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
    | gzip > "$DUMP"
  [ -s "$DUMP" ] || { echo "Kopia jest pusta: $DUMP" >&2; exit 1; }
  chmod 600 "$DUMP"
  echo "  $DUMP ($(du -h "$DUMP" | cut -f1))"
  # Not longer than backups are promised to live (LEGAL_BACKUP_DAYS).
  KEEP_DAYS="$(env_value LEGAL_BACKUP_DAYS)"
  find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime +"${KEEP_DAYS:-7}" -delete
  if [ -x deploy/backup.sh ]; then
    ./deploy/backup.sh || warn "deploy/backup.sh zakończył się błędem – kopia bazy jest wyżej."
  fi
fi

step "2. Kod z GitHuba"
git fetch --quiet origin main
NEW_COMMITS="$(git log --oneline HEAD..origin/main)"
if [ -z "$NEW_COMMITS" ]; then
  echo "  Brak nowych zmian – odświeżam kontenery i synchronizację."
else
  echo "$NEW_COMMITS" | sed 's/^/  /'
fi
git merge --ff-only --quiet origin/main
CURRENT="$(git rev-parse --short HEAD)"

step "3. Obraz i sprawdzenie ustawień"
if [ "$UPDATE_IMAGES" = 1 ]; then
  docker compose pull db redis
fi
docker compose build --pull
# Settings are checked before anything is switched: a wrong .env value
# (e.g. a legal document date) stops here, with the old site still running.
docker compose run --rm --no-deps web python manage.py check --deploy --fail-level ERROR

step "4. Migracje i nowe kontenery"
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --remove-orphans

step "5. Czy strona odpowiada"
SITE_HOST="$(env_value SITE_URL | sed -E 's#^https?://##; s#/.*$##')"
for attempt in $(seq 1 30); do
  if curl -fsS -o /dev/null -H "Host: ${SITE_HOST:-localhost}" \
       -H "X-Forwarded-Proto: https" "$HEALTH_URL"; then
    echo "  OK"
    break
  fi
  if [ "$attempt" = 30 ]; then
    echo "Strona nie odpowiada po 60 s." >&2
    docker compose logs --tail 50 web >&2
    false
  fi
  sleep 2
done

step "6. Stripe, dokumenty prawne, faktury"
docker compose exec -T web python manage.py post_deploy

# Cloudflare in front: nginx needs its current address list for real IPs.
if grep -qi cloudflare <<<"$(env_value LEGAL_CDN_PROVIDER)"; then
  SNIPPET=/etc/nginx/snippets/cloudflare-real-ip.conf
  if [ ! -f "$SNIPPET" ]; then
    warn "Brak $SNIPPET – IP odwiedzających są adresami Cloudflare (README: „Cloudflare przed serwerem”)."
  elif [ -n "$(find "$SNIPPET" -mtime +35)" ]; then
    # Updated by root's cron (README: „Cloudflare przed serwerem”) - an old
    # file means the cron doesn't run.
    warn "Lista adresów Cloudflare ma ponad 35 dni – czy działa /etc/cron.d/cloudflare-ips? Ręcznie: sudo /usr/local/sbin/update-cloudflare-ips"
  fi
fi

docker image prune -f >/dev/null

trap - ERR
echo
echo "=========================================="
echo "  monituj.pl zaktualizowany: $PREVIOUS → $CURRENT"
echo "=========================================="
