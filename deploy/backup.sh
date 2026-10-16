#!/usr/bin/env bash
# Nightly backup of the judge stack: a PostgreSQL dump and the artifact store, taken together
# so every published digest in the database still matches its file. Keeps the newest KEEP
# complete sets; a failed run leaves nothing behind and never displaces a good set.
#
#   sudo bash deploy/backup.sh            # run once
#   sudo bash deploy/backup.sh --install  # also install /etc/cron.d/shiftguard-backup
#                                         # (03:15 system time; warns unless the system is UTC)
#
# Uses only the running containers (no extra images). Never prints credentials.
set -euo pipefail
APP_DIR="${SHIFTGUARD_DIR:-/opt/shiftguard}"
DEST="${SHIFTGUARD_BACKUP_DIR:-/opt/shiftguard-backups}"
KEEP="${SHIFTGUARD_BACKUP_KEEP:-7}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "SHIFTGUARD_BACKUP_KEEP must be a positive integer" >&2; exit 2; }
compose() { docker compose -f "$APP_DIR/deploy/compose.judge.yaml" "$@"; }

if [ "${1:-}" = "--install" ]; then
  # Ubuntu's cron ignores CRON_TZ: the schedule follows the system timezone, so check it.
  tz="$(timedatectl show -p Timezone --value 2>/dev/null || date +%Z)"
  case "$tz" in
    UTC|Etc/UTC|GMT|Etc/GMT) ;;
    *) echo "warning: system timezone is $tz, so 03:15 below is $tz, not UTC" >&2 ;;
  esac
  printf '15 3 * * * root bash %s/deploy/backup.sh >> /var/log/shiftguard-backup.log 2>&1\n' "$APP_DIR" \
    > /etc/cron.d/shiftguard-backup
  chmod 0644 /etc/cron.d/shiftguard-backup
  echo "installed /etc/cron.d/shiftguard-backup (03:15 $tz)"
fi

umask 077
mkdir -p "$DEST"
chmod 0700 "$DEST"
# One backup at a time; a second concurrent run exits quietly.
exec 9>"$DEST/.lock"
flock -n 9 || { echo "another backup is running" >&2; exit 0; }
# Leftovers from a killed run (power loss, SIGKILL) are never counted; remove them after a day.
find "$DEST" -mindepth 1 -maxdepth 1 -type d -name '.partial-*' -mmin +1440 -exec rm -rf -- {} +
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
partial="$(mktemp -d "$DEST/.partial-$stamp.XXXXXX")"
trap 'rm -rf -- "$partial"' EXIT
cd "$APP_DIR"
compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$partial/postgres.dump"
# Snapshot the artifact store; published artifacts are immutable, so a changing file can only
# be in-flight staging, which tar reports (exit 1) and we treat as a failed set.
compose exec -T worker tar -czf - -C /app/var artifacts > "$partial/artifacts.tar.gz"
# The dump must be readable by pg_restore before the set may replace anything.
compose exec -T postgres pg_restore --list < "$partial/postgres.dump" > /dev/null \
  || { echo "$(date -u +%FT%TZ) backup $stamp: pg_restore --list failed; discarding set" >&2; exit 1; }
git -C "$APP_DIR" rev-parse HEAD > "$partial/source-commit.txt"
( cd "$partial" && sha256sum postgres.dump artifacts.tar.gz source-commit.txt > SHA256SUMS )
[ ! -e "$DEST/$stamp" ] || { echo "backup set $stamp already exists" >&2; exit 1; }
mv -T -- "$partial" "$DEST/$stamp"
trap - EXIT
echo "$(date -u +%FT%TZ) backup $stamp: $(du -sh "$DEST/$stamp" | cut -f1)"

# Retention: only completed, stamp-named sets count; keep the newest $KEEP.
find "$DEST" -mindepth 1 -maxdepth 1 -type d \
  -name '20[0-9][0-9][01][0-9][0-3][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z' -print0 \
  | sort -z | head -z -n -"$KEEP" | xargs -0 -r rm -rf --
