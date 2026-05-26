#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/customer-workspace"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$DATA_DIR/team_workspace.sqlite3"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
  echo "Database file not found: $DB_FILE"
  exit 1
fi

cp "$DB_FILE" "$BACKUP_DIR/team_workspace-$STAMP.sqlite3"

find "$BACKUP_DIR" -type f -name 'team_workspace-*.sqlite3' -mtime +14 -delete

echo "Backup completed: $BACKUP_DIR/team_workspace-$STAMP.sqlite3"
