#!/usr/bin/env bash
# Restore an encrypted Postgres dump from S3.
# Required: TARGET_DATABASE_URL, S3_BACKUP_BUCKET, BACKUP_OBJECT, AGE_IDENTITY_FILE (age private key).
#
# DANGEROUS — runs against TARGET_DATABASE_URL. Use against staging first.
set -euo pipefail

: "${TARGET_DATABASE_URL:?TARGET_DATABASE_URL is required}"
: "${S3_BACKUP_BUCKET:?S3_BACKUP_BUCKET is required}"
: "${BACKUP_OBJECT:?BACKUP_OBJECT is required (S3 key, e.g. backups/cm-20260514T...dump.age)}"
: "${AGE_IDENTITY_FILE:?AGE_IDENTITY_FILE is required (path to age private key)}"

tmp_enc="$(mktemp /tmp/cm-restore-XXXXXX.age)"
tmp_dump="$(mktemp /tmp/cm-restore-XXXXXX.dump)"
trap 'rm -f "$tmp_enc" "$tmp_dump"' EXIT

echo "[restore] downloading s3://${S3_BACKUP_BUCKET}/${BACKUP_OBJECT}"
aws s3 cp "s3://${S3_BACKUP_BUCKET}/${BACKUP_OBJECT}" "$tmp_enc" --no-progress
echo "[restore] decrypting"
age -d -i "$AGE_IDENTITY_FILE" "$tmp_enc" > "$tmp_dump"
echo "[restore] restoring → ${TARGET_DATABASE_URL%@*}@..."
pg_restore --clean --if-exists --no-owner --no-acl --jobs=4 --dbname="$TARGET_DATABASE_URL" "$tmp_dump"
echo "[restore] done"
