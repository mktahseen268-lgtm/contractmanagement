#!/usr/bin/env bash
#
# Post-deploy smoke test. Exits non-zero if the deployment is not actually serving.
#
# Deliberately small. A smoke test that runs the full journey takes minutes, needs credentials,
# and fails for reasons that have nothing to do with the deploy — so it gets disabled. This
# checks the handful of things that distinguish "the pods are running" from "the system works",
# and nothing else.
#
#   ./smoke-test.sh https://cm-uat.mmbl.internal

set -euo pipefail

BASE="${1:?usage: smoke-test.sh <base-url>}"
TIMEOUT="${SMOKE_TIMEOUT:-10}"
RETRIES="${SMOKE_RETRIES:-10}"

pass=0
fail=0

check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  ok    %s\n' "${name}"
    pass=$((pass + 1))
  else
    printf '  FAIL  %s\n' "${name}"
    fail=$((fail + 1))
  fi
}

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time "${TIMEOUT}" "$1"
}

expect_code() {
  local url="$1" want="$2"
  [ "$(http_code "${url}")" = "${want}" ]
}

echo "Smoke test against ${BASE}"

# ── 1. Readiness, with retries ────────────────────────────────────────────────────────────
# `/healthz/ready` answers only once migrations have run and the database is reachable, which
# is why it is the gate rather than `/health`. Retried because a rollout finishing and the
# first pod passing its readiness probe are not the same instant.
echo "Waiting for readiness…"
ready=0
for i in $(seq 1 "${RETRIES}"); do
  if [ "$(http_code "${BASE}/healthz/ready")" = "200" ]; then
    ready=1
    echo "  ready after ${i} attempt(s)"
    break
  fi
  sleep 5
done
if [ "${ready}" != "1" ]; then
  echo "  FAIL  never became ready after ${RETRIES} attempts"
  exit 1
fi

# ── 2. The things that break independently of the pods being up ───────────────────────────
check "liveness"                     expect_code "${BASE}/health" 200
check "openapi is generated"         expect_code "${BASE}/openapi.json" 200
check "metrics are exported"         expect_code "${BASE}/metrics" 200

# The signing portal is unauthenticated and is the surface a customer hits. A 500 here is an
# outage for people who cannot phone the helpdesk.
check "signing portal responds"      bash -c "[ \"\$(curl -sS -o /dev/null -w '%{http_code}' --max-time ${TIMEOUT} '${BASE}/sign/smoke-test-not-a-real-token/view' -X POST)\" -lt 500 ]"

# Authentication must refuse, not error. A 500 on a bad credential usually means the database
# or the secret store is unreachable, which a readiness probe can miss.
check "auth refuses cleanly"         bash -c "[ \"\$(curl -sS -o /dev/null -w '%{http_code}' --max-time ${TIMEOUT} -X POST '${BASE}/auth/login' -H 'Content-Type: application/json' -d '{\"email\":\"smoke@invalid.test\",\"password\":\"wrong\"}')\" -lt 500 ]"

# An unauthenticated request to a protected route must be 401, not 200. If this ever passes
# with a 200 the deployment is serving data to anonymous callers.
check "protected routes require auth" expect_code "${BASE}/contracts" 401

# ── 3. Security headers survived the gateway configuration ────────────────────────────────
headers="$(curl -sSI --max-time "${TIMEOUT}" "${BASE}/health" || true)"
check "HSTS present"                 bash -c "echo '${headers}' | grep -qi 'strict-transport-security'"
check "content-type sniffing off"    bash -c "echo '${headers}' | grep -qi 'x-content-type-options'"
check "frame options set"            bash -c "echo '${headers}' | grep -qiE 'x-frame-options|content-security-policy'"

# ── 4. PKI, because a signing deployment with an unhealthy CA is a broken deployment ──────
pki_code="$(http_code "${BASE}/pki/health")"
if [ "${pki_code}" = "200" ] || [ "${pki_code}" = "401" ]; then
  printf '  ok    PKI endpoint responds (%s)\n' "${pki_code}"
  pass=$((pass + 1))
else
  printf '  FAIL  PKI endpoint returned %s\n' "${pki_code}"
  fail=$((fail + 1))
fi

echo
echo "${pass} passed, ${fail} failed"
[ "${fail}" -eq 0 ]
