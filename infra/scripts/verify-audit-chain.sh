#!/usr/bin/env bash
#
# Verify the audit hash chain after a deployment.
#
# Runs because a migration that touches `audit_log` and breaks the chain would otherwise be
# found by an auditor rather than by us — months later, on the period nobody can now reconstruct.
# It costs one authenticated request per tenant.
#
#   AUDIT_VERIFY_TOKEN=<api key> ./verify-audit-chain.sh https://cm-uat.mmbl.internal
#
# The token needs the `audit.verify` permission and nothing else. Give it its own API key rather
# than reusing an administrator's: this runs unattended in a pipeline, and a key that can only
# verify a hash chain is a key worth far less to whoever finds it in a log.

set -euo pipefail

BASE="${1:?usage: verify-audit-chain.sh <base-url>}"
TOKEN="${AUDIT_VERIFY_TOKEN:-}"
TIMEOUT="${VERIFY_TIMEOUT:-60}"

if [ -z "${TOKEN}" ]; then
  # Not a hard failure. A deployment should not be blocked because a verification credential
  # was not configured — but it must be loud, because a check that silently does not run is
  # worse than one that was never added.
  echo "::warning::AUDIT_VERIFY_TOKEN is not set — the audit chain was NOT verified."
  echo "::warning::Configure an API key with the audit.verify permission to enable this gate."
  exit 0
fi

echo "Verifying the audit chain at ${BASE}"

response="$(curl -sS --max-time "${TIMEOUT}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json" \
  "${BASE}/audit/verify" || true)"

if [ -z "${response}" ]; then
  echo "::error::No response from /audit/verify. The chain could not be verified."
  exit 1
fi

# Parsed with python rather than grep. A chain report is structured, and grepping for the
# string "true" in JSON finds it inside a field that means something else.
python3 - "$response" <<'PY'
import json
import sys

raw = sys.argv[1]
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print(f"::error::/audit/verify did not return JSON: {raw[:300]}")
    sys.exit(1)

# The endpoint reports per tenant. A single tenant response is accepted too, so this works on a
# single-tenant on-prem profile without special-casing.
results = data if isinstance(data, list) else [data]

broken = []
checked = 0
skipped = 0

for entry in results:
    tenant = entry.get("tenant_id", "(single tenant)")
    ok = entry.get("ok", entry.get("valid"))
    problems = entry.get("problems") or []
    total = entry.get("checked", entry.get("entries"))

    if ok is None:
        print(f"::warning::Unrecognised response shape for {tenant}; treating as unverified.")
        skipped += 1
        continue

    checked += 1
    if ok:
        suffix = f" ({total} entries)" if total is not None else ""
        print(f"  ok    {tenant}{suffix}")
    else:
        broken.append((tenant, problems))
        print(f"  BROKEN {tenant}")
        for p in problems[:5]:
            print(f"         first break: {p}")

print()
if broken:
    print(f"::error::The audit chain is broken for {len(broken)} tenant(s).")
    print("::error::This is a P1. Identify the first broken entry, recover the preceding state")
    print("::error::from the pre-deploy backup, and report it within the SLA.")
    sys.exit(1)

if checked == 0:
    print("::warning::No tenant chains were checked.")
    sys.exit(0)

print(f"Audit chain verified for {checked} tenant(s).")
PY
