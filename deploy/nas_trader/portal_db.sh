#!/bin/bash
# The portal database's lines in /volume1/docker/trader/.env (W10-0013 sub 13). Run with sudo on the NAS. Prints no secret.
#
#   sudo bash portal_db.sh password   make PORTAL_DB_PASSWORD (random, hex) if there is none yet
#   sudo bash portal_db.sh switch     point RELAY_DATABASE_URL at portal-db; the old (Neon) line is kept as NEON_DATABASE_URL
#   sudo bash portal_db.sh rollback   put the Neon line back as RELAY_DATABASE_URL
#   sudo bash portal_db.sh status     which database the relay is set to (names only)
#
# ENV_FILE overrides the file (tests). The file stays mode 600.
set -eu
ENV_FILE="${ENV_FILE:-/volume1/docker/trader/.env}"
cmd="${1:-status}"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE" >&2; exit 1; }

val() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
count() { grep -c -E "^$1=." "$ENV_FILE" || true; }
# rewrite KEY=VALUE (drops every old KEY line, appends the new one)
setkey() {
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  grep -v -E "^$1=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

case "$cmd" in
  password)
    if [ "$(count PORTAL_DB_PASSWORD)" -ge 1 ]; then echo "PORTAL_DB_PASSWORD already set (not changed)"; exit 0; fi
    pw="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    setkey PORTAL_DB_PASSWORD "$pw"
    echo "PORTAL_DB_PASSWORD written (${#pw} characters)"
    ;;
  switch)
    pw="$(val PORTAL_DB_PASSWORD)"
    [ -n "$pw" ] || { echo "run 'password' first" >&2; exit 1; }
    cur="$(val RELAY_DATABASE_URL)"
    case "$cur" in
      *@portal-db:*) echo "RELAY_DATABASE_URL already points at portal-db"; exit 0;;
    esac
    [ -z "$cur" ] || setkey NEON_DATABASE_URL "$cur"
    setkey RELAY_DATABASE_URL "postgresql://portal:$pw@portal-db:5432/portal"
    echo "RELAY_DATABASE_URL now points at portal-db; the old line is saved as NEON_DATABASE_URL"
    ;;
  rollback)
    old="$(val NEON_DATABASE_URL)"
    [ -n "$old" ] || { echo "no NEON_DATABASE_URL line to go back to" >&2; exit 1; }
    setkey RELAY_DATABASE_URL "$old"
    echo "RELAY_DATABASE_URL is back on the old (Neon) database"
    ;;
  status)
    cur="$(val RELAY_DATABASE_URL)"
    case "$cur" in
      "") echo "relay: no history database";;
      *@portal-db:*) echo "relay: portal-db (NAS)";;
      *) echo "relay: another database (Neon)";;
    esac
    echo "PORTAL_DB_PASSWORD lines: $(count PORTAL_DB_PASSWORD)   NEON_DATABASE_URL lines: $(count NEON_DATABASE_URL)"
    ;;
  *) echo "usage: portal_db.sh password|switch|rollback|status" >&2; exit 2;;
esac
