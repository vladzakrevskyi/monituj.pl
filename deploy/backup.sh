#!/usr/bin/env bash
# Daily backup of the database and uploaded files.
# Usage (cron): 30 3 * * * /srv/monituj/deploy/backup.sh >> /var/log/monituj-backup.log 2>&1
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/monituj}"
# Keep in line with LEGAL_BACKUP_DAYS - the privacy policy promises it.
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M)"

cd "$APP_DIR"
env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }
POSTGRES_USER="$(env_value POSTGRES_USER)"
POSTGRES_DB="$(env_value POSTGRES_DB)"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
    > "$BACKUP_DIR/db_$STAMP.dump"

docker run --rm \
    -v monituj_storage:/data:ro \
    -v "$BACKUP_DIR":/backup \
    alpine tar czf "/backup/storage_$STAMP.tar.gz" -C /data .

find "$BACKUP_DIR" -type f -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $STAMP"
