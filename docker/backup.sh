#!/bin/sh
# Daily Postgres backup with simple rotation (keep last 7). Runs on the HOST
# via cron -- not a container in docker-compose.yml, pg_dump only needs
# `docker compose exec`, no extra service needed. Location-independent: paths
# are resolved relative to this script, not the caller's working directory,
# so cron can invoke it by absolute path regardless of the crontab's own cwd.
#
# Covers crash/corruption/human-error recovery, NOT total server/disk loss --
# off-site copies are a deliberate future item, not built here. See DEPLOY.md.
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_DIR"

BACKUP_DIR="${BACKUP_DIR:-$HOME/trading-bot-backups}"
KEEP=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

docker compose exec -T db pg_dump -U postgres trading_bot > "$BACKUP_DIR/trading_bot_${TIMESTAMP}.sql"

# Rotation: keep only the most recent $KEEP dumps.
ls -1t "$BACKUP_DIR"/trading_bot_*.sql 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm --
