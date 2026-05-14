# 21 · DevSecOps Plan

The pipeline is defined in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Mirrors are
also provided for **GitLab CI** ([`.gitlab-ci.yml`](../.gitlab-ci.yml)) and **Azure DevOps**
([`azure-pipelines.yml`](../azure-pipelines.yml)) — pick whichever your org standardises on.

## 1. Environment segregation

| Env | Purpose | Branch / promotion | Notes |
|---|---|---|---|
| **dev** | Developer laptops, ephemeral CI runs | feature branches | docker-compose; `ENV=dev` |
| **uat / staging** | Pre-release verification, QA, security testing (DAST, VAPT prep) | `main` after CI pass | same image, prod-like config; anonymised data refresh weekly |
| **production** | Customer traffic | promoted from staging after sign-off + tag | manual approval gate; cosign-verified images only |

Each environment has its **own** Postgres / Redis / S3 / secrets manager namespace. Cross-env
secrets sharing is prohibited.

## 2. CI Pipeline (per PR + per merge)

```
┌─ lint ──────────────────────────────────────────────────────────────────┐
│  ruff (python)  ·  mypy --strict-optional  ·  next lint  ·  prettier    │
└─────────────────────────────────────────────────────────────────────────┘
┌─ test ──────────────────────────────────────────────────────────────────┐
│  pytest -q (api)  ·  next build (web)  ·  postgres+redis containers     │
└─────────────────────────────────────────────────────────────────────────┘
┌─ SAST ──────────────────────────────────────────────────────────────────┐
│  bandit -r app -lll          (python static analysis)                   │
│  semgrep --config=p/owasp-top-ten (multi-language ruleset)              │
└─────────────────────────────────────────────────────────────────────────┘
┌─ Dependency scan ───────────────────────────────────────────────────────┐
│  pip-audit         (python CVE/advisory check, OSV-backed)              │
│  safety            (PyUp DB)                                            │
│  npm audit --audit-level=high                                           │
└─────────────────────────────────────────────────────────────────────────┘
┌─ Secrets scan ──────────────────────────────────────────────────────────┐
│  gitleaks  ·  trufflehog                                                │
└─────────────────────────────────────────────────────────────────────────┘
┌─ Container build + scan ────────────────────────────────────────────────┐
│  docker buildx ·  trivy image (HIGH/CRITICAL fail the build)            │
└─────────────────────────────────────────────────────────────────────────┘
┌─ Release ───────────────────────────────────────────────────────────────┐
│  cosign sign  ·  SBOM (syft)  ·  push to registry  ·  GitHub release    │
└─────────────────────────────────────────────────────────────────────────┘
```

DAST is run on the **staging** deployment, not in PR — `zap-baseline.py -t https://staging.…`
is wired to a nightly GitHub Action (`.github/workflows/dast-nightly.yml`).

## 3. SAST tools we use

- **bandit** — Python AST scanner (eval, exec, hardcoded passwords, weak hashes, …).
- **semgrep** — community OWASP Top-10 ruleset for both Python and TS.
- **pip-audit / safety** — CVE database for installed deps.
- **gitleaks / trufflehog** — secrets-in-history scanning.

False-positives are managed via `.bandit`, `.semgrepignore`, and per-CVE allow-list in
`pip-audit-config.toml` — each suppression carries a justification and an owner.

## 4. DAST + VAPT

- **Nightly DAST**: ZAP Baseline scan against staging. Alerts file an issue with the OWASP CRS
  category and CVSS estimate.
- **Quarterly VAPT**: a 3rd-party penetration test engagement (NIIT / Trail of Bits / Coalfire
  class). Scope: web app + API + cloud surface + signing portal.
- The platform supports a **maintenance window mode** for VAPT: a feature flag exposes test
  endpoints (e.g. ability to bypass MFA with a one-time pen-test token) which are disabled
  outside the window. The mode itself is audited and time-bound (max 8 h).

## 5. Vulnerability Remediation SLAs

| Severity (CVSS v3.1) | Triage | Patch / Mitigation |
|---|---|---|
| **Critical** (9.0–10.0) | Within 4 h | **48 h** to patch + verify |
| **High** (7.0–8.9) | Within 24 h | **6 days** |
| **Medium** (4.0–6.9) | Within 3 days | **15 days** |
| **Low** (0.1–3.9) | Within 7 days | **30 days** |
| Informational | Backlog | Bundled into next minor |

These SLAs are encoded in the GitHub label set (`sec:critical`, `sec:high`, etc.) which the
auto-stale-bot honours when re-opening past-due tickets.

## 6. Patch Management

- **OS / base image**: `apps/api/Dockerfile` and `apps/web/Dockerfile` use `python:3.12-slim`
  and `node:20-alpine` digest-pinned. Dependabot bumps the digest weekly; CI re-runs the full
  suite + Trivy. A "base-image-update" job rebuilds + redeploys staging on green.
- **Python deps**: Dependabot weekly. Locked via pip's hash-checking in production.
- **NPM deps**: Dependabot weekly with `package-lock.json` exact lockfile.
- **Critical advisories**: GitHub Security Alerts → Slack `#security-alerts` → Jira ticket
  auto-created with the SLA above.

## 7. Code-review policy

- Every change in `main` requires **at least one** review.
- Security-sensitive paths (`app/security.py`, `app/auth_service.py`, `app/middleware/*`,
  `app/deps.py`, every `migrations/versions/*`) require **two** reviews, one from the
  Security WG.
- Branch protection on `main`: required CI green, signed commits, conversation resolution,
  linear history.

## 8. Secrets in CI

Secrets in GitHub Actions are stored in repository-level **Encrypted Secrets**, masked in logs.
Production deploy uses **OIDC federation** with the cloud provider (no static cloud keys in CI):
- AWS: `aws-actions/configure-aws-credentials` with `role-to-assume` and `id-token: write`.
- Azure: `azure/login` with federated identity.
- GCP: `google-github-actions/auth` with WIF.

## 9. Release checklist (used by RM on every prod release)

```
☐ All CI jobs green on the tagged commit
☐ Image built, scanned (no HIGH/CRITICAL), cosign-signed, pushed
☐ SBOM attached to the GitHub Release
☐ DB migration plan: forward-only, reviewed by DBA, dry-run in staging
☐ Backup verified <24 h old before deploy
☐ Feature flags reviewed; defaults safe
☐ Roll-back plan written (previous image tag + previous migration revision)
☐ Monitoring: dashboards open, alerts armed
☐ Communications: customer release notes drafted, security advisories filed if any
```
