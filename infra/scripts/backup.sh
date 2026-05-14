#!/usr/bin/env bash
# Encrypted Postgres backup → S3. Run nightly from cron / k8s CronJob.
# Required env: DATABASE_URL, S3_BACKUP_BUCKET, AGE_RECIPIENT (age recipient string).
# Optional:    S3_BACKUP_PREFIX (default: backups), KEEP_DAYS (default: 35).
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${S3_BACKUP_BUCKET:?S3_BACKUP_BUCKET is required}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT is required (age key, e.g. age1xxxxxx...)}"
S3_BACKUP_PREFIX="${S3_BACKUP_PREFIX:-backups}"
KEEP_DAYS="${KEEP_DAYS:-35}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="cm-${stamp}.dump.age"

echo "[backup] dumping ${DATABASE_URL%@*}@... → ${out}"
pg_dump --no-owner --no-acl --format=custom --compress=9 "$DATABASE_URL" \
  | age -r "$AGE_RECIPIENT" -o "$out"

size=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out")
echo "[backup] uploading ${out} (${size} bytes) to s3://${S3_BACKUP_BUCKET}/${S3_BACKUP_PREFIX}/"
aws s3 cp "$out" "s3://${S3_BACKUP_BUCKET}/${S3_BACKUP_PREFIX}/${out}" \
  --no-progress \
  --metadata "backup-utc=${stamp},source=$(hostname -s)" \
  --acl bucket-owner-full-control

# Local cleanup
rm -f "$out"

# Retention — drop S3 objects older than KEEP_DAYS (lifecycle policy is preferred for prod)
cutoff_epoch=$(date -u -d "${KEEP_DAYS} days ago" +%s 2>/dev/null \
  || date -u -v-${KEEP_DAYS}d +%s)
aws s3api list-objects-v2 \
  --bucket "$S3_BACKUP_BUCKET" \
  --prefix "${S3_BACKUP_PREFIX}/cm-" \
  --query "Contents[].{Key:Key,LastModified:LastModified}" \
  --output text 2>/dev/null | while read -r key lm; do
    [ -z "$key" ] && continue
    lm_epoch=$(date -u -d "$lm" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%S+00:00" "${lm%+*}+00:00" +%s 2>/dev/null || echo 0)
    if [ "$lm_epoch" -lt "$cutoff_epoch" ]; then
        echo "[backup] retention: deleting $key (older than ${KEEP_DAYS}d)"
        aws s3 rm "s3://${S3_BACKUP_BUCKET}/${key}"
    fi
done

echo "[backup] done — ${out}"
