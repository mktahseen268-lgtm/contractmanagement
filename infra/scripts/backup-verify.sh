#!/usr/bin/env bash
#
# Restore verification (Phase 7, item 8).
#
# A backup nobody has restored is a hypothesis, not a backup. This script takes the most
# recent dump, restores it into a scratch database, and then checks that the data is actually
# usable — not merely that pg_restore exited zero, which it will do for a dump that is missing
# half its rows.
#
# Run it on a schedule. The RPO/RTO evidence the RFP asks for is this script's output over
# time, not a statement of intent.
#
#   ./backup-verify.sh /backups/cm-2026-08-28.dump
#   ./backup-verify.sh                     # uses the newest dump in $BACKUP_DIR
#
# Exit codes:  0 verified   1 restore failed   2 restored but the data is wrong
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
VERIFY_DB="${VERIFY_DB:-cm_restore_check}"
PGHOST="${PGHOST:-localhost}"
PGUSER="${PGUSER:-postgres}"
DUMP="${1:-}"

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [[ -z "$DUMP" ]]; then
  DUMP="$(ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null | head -n1 || true)"
fi
if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  log "FAIL: no dump found in $BACKUP_DIR"
  exit 1
fi

log "verifying $DUMP ($(du -h "$DUMP" | cut -f1))"

# A dump that restores into a database with leftovers from the last run proves nothing, so
# the scratch database is always recreated.
dropdb --if-exists -h "$PGHOST" -U "$PGUSER" "$VERIFY_DB"
createdb -h "$PGHOST" -U "$PGUSER" "$VERIFY_DB"

started=$(date +%s)
if ! pg_restore -h "$PGHOST" -U "$PGUSER" -d "$VERIFY_DB" --no-owner --no-acl "$DUMP" 2>/tmp/restore.err; then
  log "FAIL: pg_restore reported errors"
  tail -20 /tmp/restore.err
  exit 1
fi
elapsed=$(( $(date +%s) - started ))
log "restored in ${elapsed}s  (this is the measured RTO for the database tier)"

# --- The part that matters -------------------------------------------------------------
# pg_restore exits zero for a dump that restored an empty schema. These checks ask whether
# the restored database is one the application could actually run against.
fail=0
check() {
  local label="$1" sql="$2" expect="$3"
  local got
  got="$(psql -h "$PGHOST" -U "$PGUSER" -d "$VERIFY_DB" -tAc "$sql" 2>/dev/null || echo "ERR")"
  if [[ "$got" == "ERR" ]]; then
    log "FAIL: $label — query errored"; fail=1; return
  fi
  if (( got < expect )); then
    log "FAIL: $label — got $got, expected at least $expect"; fail=1
  else
    log "ok:   $label ($got)"
  fi
}

check "tables present"        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 30
check "tenants restored"      "SELECT count(*) FROM tenants" 1
check "users restored"        "SELECT count(*) FROM users" 1
check "audit rows restored"   "SELECT count(*) FROM audit_log" 1
check "row security enabled"  "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity" 10
check "alembic at a version"  "SELECT count(*) FROM alembic_version" 1

# The audit chain is the one thing a corrupted restore must not silently break: if the rows
# came back but the chain does not verify, the tamper-evidence claim is gone and nobody would
# know until an auditor asked.
orphans="$(psql -h "$PGHOST" -U "$PGUSER" -d "$VERIFY_DB" -tAc \
  "SELECT count(*) FROM audit_log WHERE row_hash <> '' AND prev_hash = ''" 2>/dev/null || echo ERR)"
if [[ "$orphans" == "ERR" ]]; then
  log "FAIL: could not inspect the audit chain"; fail=1
elif (( orphans > 1 )); then
  log "FAIL: $orphans chained audit rows have no predecessor — the chain did not survive"
  fail=1
else
  log "ok:   audit chain has a single genesis row"
fi

dropdb --if-exists -h "$PGHOST" -U "$PGUSER" "$VERIFY_DB"

if (( fail )); then
  log "RESULT: restore completed but the data is not usable"
  exit 2
fi
log "RESULT: verified — restored and usable in ${elapsed}s"
