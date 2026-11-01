#!/bin/bash
# Daily pg_dump of the portal's Postgres (W10-0013 sub 13). Runs as the container `trader-portal-db-backup`.
# Every hour: if no good dump in /backup is under 23 h old, dump now. Each dump is checked with pg_restore --list before it is
# kept; a failed one is deleted and retried next hour. Dumps older than KEEP_DAYS (14) are removed, never the newest 3.
# Reads PGHOST / PGUSER / PGDATABASE / PGPASSWORD from the environment; writes only /backup. `once` = one pass, then exit.
set -u
BACKUP_DIR="${BACKUP_DIR:-/backup}"
KEEP_DAYS="${KEEP_DAYS:-14}"
EVERY_S="${EVERY_S:-3600}"
MAX_AGE_MIN="${MAX_AGE_MIN:-1380}"

pass() {
  if [ -n "$(find "$BACKUP_DIR" -maxdepth 1 -name 'portal-*.dump' -mmin "-$MAX_AGE_MIN" 2>/dev/null | head -1)" ]; then
    return 0
  fi
  stamp="$(date -u +%Y%m%d-%H%M)"
  tmp="$BACKUP_DIR/.portal-$stamp.partial"
  if pg_dump -Fc -f "$tmp" && pg_restore --list "$tmp" > /dev/null 2>&1; then
    mv "$tmp" "$BACKUP_DIR/portal-$stamp.dump"
    echo "$(date -u +%FT%TZ) backup ok: portal-$stamp.dump ($(wc -c < "$BACKUP_DIR/portal-$stamp.dump") bytes)"
  else
    echo "$(date -u +%FT%TZ) backup FAILED (pg_dump or the restore check); will retry"
    rm -f -- "$tmp"
    return 1
  fi
  # prune: older than KEEP_DAYS, but keep the newest 3 whatever their age
  ls -1t "$BACKUP_DIR"/portal-*.dump 2>/dev/null | tail -n +4 | while read -r f; do
    if [ -n "$(find "$f" -mtime "+$KEEP_DAYS" 2>/dev/null)" ]; then rm -f -- "$f"; fi
  done
}

if [ "${1:-}" = "once" ]; then pass; exit $?; fi
while true; do
  pass || true
  sleep "$EVERY_S"
done
