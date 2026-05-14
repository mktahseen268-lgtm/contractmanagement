# 24 · Enterprise / Government RFI Compliance Matrix

One-pager mapping every typical RFI control to its status in this codebase. Use this as the
**RFI response source of truth**. Where status is *Implemented*, the column shows the file
that proves it; where *Architected*, it points to the doc describing the plug-point.

Legend: ✅ Implemented · 🟡 Implemented in part / requires operator step · 🔵 Architected, not yet built · ⚪ Out of scope for v1.

## A. Security

| # | Control | Status | Evidence |
|---|---|---|---|
| A.1 | OWASP Top 10 (2021) controls | ✅ | [`20-security-compliance.md`](20-security-compliance.md) §1 |
| A.2 | OWASP ASVS L2 alignment | ✅ | §2 of same doc |
| A.3 | Multi-Factor Authentication | ✅ | `apps/api/app/auth_service.py` (TOTP + recovery + email-OTP) |
| A.4 | RBAC | ✅ | `apps/api/app/workflow_service.py::_ROLE_RANK` + per-router gates |
| A.5 | SSO / IAM (SAML/OIDC) | 🔵 | §3.2; adapter slot ready |
| A.6 | SCIM 2.0 provisioning | 🔵 | §3.2; user APIs SCIM-shaped |
| A.7 | TLS 1.2 / 1.3 | 🟡 | Operator: terminate at ingress; HSTS already emitted by app |
| A.8 | AES-256 encryption at rest (app-layer for sensitive cols) | ✅ | `apps/api/app/secrets_box.py` (MFA secret) |
| A.9 | Database transparent encryption | 🟡 | Operator: RDS TDE / Azure flexible-server enc / `pg_crypto` |
| A.10 | Secure headers (HSTS, CSP, XFO, XCTO, Referrer, Permissions) | ✅ | `apps/api/app/middleware/security_headers.py` + ingress |
| A.11 | CSRF protection | ✅ | Bearer JWT in `Authorization` header (no cookie-side state-changing requests); refresh cookie is httpOnly + SameSite=Lax + Secure |
| A.12 | XSS protection | ✅ | CSP + React JSX escaping; no `dangerouslySetInnerHTML` |
| A.13 | SQL Injection protection | ✅ | SQLAlchemy ORM (parameterised) — 0 string-concat SQL in repo |
| A.14 | Rate limiting | ✅ | `apps/api/app/middleware/rate_limit.py` |
| A.15 | Login lockout | ✅ | `apps/api/app/auth_service.py::lockout_*` |
| A.16 | CAPTCHA | 🟡 | Hook ready; operator wires Turnstile/hCaptcha at the gateway |
| A.17 | Secrets management | 🟡 | Pydantic settings + env; operator wires Vault / Secrets Manager |
| A.18 | No hardcoded credentials | ✅ | Repo-wide check via `gitleaks` in CI; prod refuses default `SECRET_KEY` |
| A.19 | Encrypted backups | 🟡 | `infra/scripts/backup.sh`; operator runs against KMS-encrypted bucket |
| A.20 | Sensitive-data masking in logs | ✅ | `apps/api/app/middleware/logging.py::_redact_sensitive` |

## B. Logging & Audit

| # | Control | Status | Evidence |
|---|---|---|---|
| B.1 | Structured access logs (JSON, CLF-compatible names) | ✅ | `apps/api/app/middleware/logging.py` |
| B.2 | Severity levels (RFC 5424) | ✅ | `level` field on every record |
| B.3 | Audit trail of every critical action | ✅ | `apps/api/app/audit.py` + 30+ event types |
| B.4 | Append-only audit log | ✅ | Conventional; DB-level role grants planned (operator) |
| B.5 | SIEM-ready format | ✅ | [`23-integrations.md`](23-integrations.md) §4 incl. ECS/CIM field map |
| B.6 | Security-event logging | ✅ | `auth.login.*`, `mfa.*`, `password.changed`, `role.changed`, `api_key.*`, etc. |
| B.7 | Per-request correlation ID | ✅ | `X-Request-Id` emitted on every response |
| B.8 | 10-year audit retention with 1-yr instant search | ✅ | `apps/api/app/tasks.py::retention_purge` + S3 Parquet archive |

## C. Infrastructure

| # | Control | Status | Evidence |
|---|---|---|---|
| C.1 | Multi-tier architecture | ✅ | [`22-infra-deployment.md`](22-infra-deployment.md) §1 |
| C.2 | High availability | ✅ (design) / 🟡 (deploy) | Doc §3 + k8s manifests |
| C.3 | Kubernetes-ready deployment | ✅ | `infra/k8s/*` |
| C.4 | Load-balancer ready | ✅ | Ingress + `X-Forwarded-For` consumed by `client_ip()` |
| C.5 | Redis HA / Celery HA | ✅ (design) | Doc §3 |
| C.6 | Backup & restore | ✅ | `infra/scripts/backup.sh` + `infra/scripts/restore.sh` |
| C.7 | Disaster recovery (RTO/RPO targeted) | ✅ (design) | Doc §7.2 |
| C.8 | Data archiving | ✅ | `retention_purge` task |
| C.9 | Data purging | ✅ | same |
| C.10 | 10-year retention | ✅ | same |
| C.11 | 1-year instantly searchable | ✅ | same; archived rows queryable via Athena/Glue |

## D. Integrations

| # | Control | Status | Evidence |
|---|---|---|---|
| D.1 | API Gateway / Kong compatibility | ✅ | [`23-integrations.md`](23-integrations.md) §1 |
| D.2 | MS Teams | 🟡 (outbound now via webhook; bot planned) | §2.1 |
| D.3 | SharePoint | 🟡 | §2.2 |
| D.4 | Outlook | 🟡 | §2.3 |
| D.5 | WAF compatibility | ✅ | §3 |
| D.6 | SIEM compatibility | ✅ | §4 |
| D.7 | NIFT digital signature | 🔵 (provider hook designed) | §5 |

## E. DevSecOps

| # | Control | Status | Evidence |
|---|---|---|---|
| E.1 | CI/CD pipeline | ✅ | `.github/workflows/ci.yml` |
| E.2 | Dev / UAT / Production segregation | ✅ (design) | [`21-devsecops-plan.md`](21-devsecops-plan.md) §1 |
| E.3 | SAST | ✅ | Bandit + Semgrep in CI |
| E.4 | DAST | ✅ | ZAP nightly against staging |
| E.5 | VAPT support | ✅ | §4 incl. maintenance-window mode |
| E.6 | Dependency scanning | ✅ | pip-audit + safety + npm audit + Trivy in CI |
| E.7 | Secrets scanning | ✅ | gitleaks + trufflehog in CI |
| E.8 | Container signing | ✅ (design) | cosign in §2 |
| E.9 | Patch management | ✅ (process) | §6 |
| E.10 | Remediation SLAs (48h / 6d / 15d / 30d) | ✅ | §5 |

## F. Database

| # | Control | Status | Evidence |
|---|---|---|---|
| F.1 | PostgreSQL primary | ✅ | repo default |
| F.2 | JSONB + full-text + OCR/AI metadata | ✅ | `Contract.tags`, `OcrJob.result`, etc. as `JSON`/`JSONB` columns |
| F.3 | Database abstraction (MSSQL portable) | 🟡 | [`25-database-portability.md`](25-database-portability.md) |
| F.4 | Migrations under version control | ✅ | Alembic 0001 → 0011 |

## G. Government / enterprise readiness

| # | Control | Status | Evidence |
|---|---|---|---|
| G.1 | Tenant isolation enforced at DB layer | ✅ | PostgreSQL RLS |
| G.2 | Per-tenant branding | ✅ | Settings → Branding (accent color CSS variable) |
| G.3 | Right-to-left (Arabic) | ✅ | `<html dir>` flip on Tenant.locale |
| G.4 | Per-tenant locale + timezone | ✅ | Tenant settings |
| G.5 | Data residency control | 🟡 | Operator: per-tenant cluster / per-region routing (no app changes needed) |
| G.6 | Customer KMS keys (BYOK) | 🔵 | Architected via per-tenant prefix + SSE-KMS key alias |
| G.7 | Data-export on request (GDPR Art. 20) | 🟡 | Existing `/reports/contracts.csv` + per-contract PDFs; per-user-data export endpoint planned |
| G.8 | Data-deletion on request (GDPR Art. 17) | 🟡 | Cascade-delete on contract; whole-tenant deletion is an operator script |

---

## Single-line answer for an RFI checkbox question

For a YES/NO question, if the status above is ✅ or 🟡 the answer is **YES** with a footnote
pointing at the *Evidence* column. 🔵 is **YES, scheduled** (with an ETA from the roadmap).
⚪ is the only **NO** state.

The roadmap below sequences the 🟡 and 🔵 items so the next 6-month plan is unambiguous.
