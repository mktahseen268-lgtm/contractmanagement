# OWASP Top 10 and ASVS Level 2 mapping

Phase 8, item 15. Where each risk is addressed, and where it is not.

The honest framing: a mapping document is only worth reading if it says what is *missing*.
Every row below either names the code that handles the risk or says the risk is unaddressed.

## OWASP Top 10 (2021)

### A01 — Broken Access Control

The largest surface here, and the one most of Phase 8 exists for.

| Vector | Handled | Where |
|---|---|---|
| Horizontal (another tenant's data) | ✅ | Two layers: PostgreSQL RLS keyed on `app.cm_tenant`, **and** an explicit `tenant_id` filter in every repository query. Both kept deliberately — see `CLAUDE.md` |
| Vertical (privilege escalation) | ✅ | `access_control.permissions_for`; role changes require step-up |
| Object-level (guessing an id) | ✅ | Every route resolves through an `_owned` helper that checks the tenant before returning |
| Confidential records | ✅ | `ContractAccess` need-to-know; refused reads audited as `contract.access_denied` |
| Force-browsing an API a UI hides | ✅ | Every check is in the service layer. Hiding a button is not a control |
| Segregation of duties | ✅ | `access_control.SEGREGATED` |

### A02 — Cryptographic Failures

| Vector | Handled | Where |
|---|---|---|
| Secrets at rest | ✅ | `EncryptedString` (Fernet, rotatable) for MFA and webhook secrets |
| Signing-portal tokens | ✅ | SHA-256 hash stored for lookup; ciphertext for reminder use only |
| Bearer tokens (API keys, temporary links) | ✅ | Hash only. A leaked link is not replayable from a stolen database |
| Passwords | ✅ | `security.hash_password`; strength policy enforced |
| In transit | ⚙️ | TLS terminated at Kong; `COOKIE_SECURE` refused at boot in production |
| Database at rest | ⚙️ | **Operator step** — `docs/30-tde.md` |
| Document signing | ✅ | PAdES-LTV, per-signatory certificates from the in-platform CA |

### A03 — Injection

| Vector | Handled | Where |
|---|---|---|
| SQL | ✅ | SQLAlchemy parameterised throughout. The one raw fragment — the FTS predicate in `search_service` — binds its parameter and never interpolates user input |
| XML (XXE, billion laughs) | ✅ | `defusedxml` for SOAP and SAML parsing, **before** any credential check, because that parser is reachable unauthenticated |
| XML signature wrapping | ✅ | `signxml` verification; only the verified subtree is read |
| Template injection | ✅ | `merge_engine` substitutes into text, never evaluates |
| Command | ✅ | No shell invocation anywhere in the request path |

### A04 — Insecure Design

| Concern | Handled | Where |
|---|---|---|
| Approval bypass | ✅ | Lifecycle state machine; workflow blocks generic status actions while a run is active |
| Unapproved wording reaching a contract | ✅ | Templates and clauses generate from **frozen approved snapshots**, never the live row |
| Silent gaps in a generated document | ✅ | Unresolved placeholders and unresolvable clause references refuse generation rather than blanking |
| Tamper-evident record | ✅ | HMAC chain ordered by monotonic `seq` |

### A05 — Security Misconfiguration

| Concern | Handled | Where |
|---|---|---|
| Insecure defaults | ✅ | `settings.validate_for_production()` refuses to boot on the dev secret key, insecure cookies, localhost CORS or a SQLite DSN |
| Unnecessary surface | ✅ | SOAP, SAML, SIEM, ClamAV, Teams and SharePoint all off by default |
| Security headers | ✅ | `SecurityHeadersMiddleware`, plus Kong as a second layer |
| Stack traces to clients | ✅ | Generic errors; detail to the log. SAML rejections deliberately do not say why |

### A06 — Vulnerable and Outdated Components

| Control | State | Where |
|---|---|---|
| Dependency scanning | ✅ | `pip-audit`, `safety`, `npm audit` in CI |
| Container scanning | ✅ | Trivy on the API image |
| Pinned versions | ✅ | `requirements*.txt` pinned exactly |
| SBOM | ⚙️ | Generated for the PKI component (Phase 1). **Not yet for the whole application** |

### A07 — Identification and Authentication Failures

| Vector | Handled | Where |
|---|---|---|
| Credential stuffing | ⚙️ | Redis rate limiting; proof-of-work after repeated failures; lockout state |
| Weak passwords | ✅ | `validate_password_strength` — length, classes, blocklist, no name/email substrings |
| Session fixation | ✅ | Refresh-token rotation with **reuse detection** — a replayed token burns the whole chain |
| MFA | ✅ | TOTP with recovery codes, email OTP fallback |
| Phishing-resistant MFA | ❌ | **FIDO2/WebAuthn not implemented** — Phase 8, item 1 |
| SSO assertion forgery | ✅ | See `test_saml.py`: unsigned, wrong-key, tampered, wrong-audience and replayed assertions all rejected |

### A08 — Software and Data Integrity Failures

| Concern | Handled | Where |
|---|---|---|
| Audit tampering | ✅ | HMAC chain; `verify_chain` detects deletion and edit |
| Unsigned updates to approved content | ✅ | Editing approved wording returns it to draft |
| Deserialisation | ✅ | No pickle anywhere; JSON only |
| Webhook authenticity | ✅ | HMAC-signed deliveries with a timestamp |

### A09 — Security Logging and Monitoring Failures

| Concern | Handled | Where |
|---|---|---|
| Every state change logged | ✅ | `add_audit_entry` is the contract; enforced by convention and reviewed |
| Log integrity | ✅ | The chain |
| Centralised monitoring | ⚙️ | SIEM feed, `SIEM_ENABLED` |
| Alerting | ⚙️ | Prometheus `/metrics`; **alert rules are an operator artefact** |
| Failed access attempts recorded | ✅ | `contract.access_denied`, `sod.blocked`, `stepup.failed`, `auth.saml_rejected` |

### A10 — Server-Side Request Forgery

| Vector | Handled | Where |
|---|---|---|
| Webhook URLs | ⚙️ | Residency allowlist resolves and rejects public addresses unless explicitly permitted |
| SIEM / SMS / SharePoint / Teams endpoints | ⚙️ | Same gate |
| OIDC/SAML metadata fetch | ⚙️ | Same gate |
| User-supplied URL fetching | ✅ | The application does not fetch arbitrary user-supplied URLs anywhere |

## ASVS Level 2 — where we stand

Rather than reproducing 280 rows, the chapters that matter and their state:

| Chapter | State | Note |
|---|---|---|
| V1 Architecture | ✅ | Documented in `CLAUDE.md`, `docs/` |
| V2 Authentication | 🟡 | Strong except V2.2.2 (phishing-resistant factor) — FIDO2 missing |
| V3 Session management | ✅ | Rotation, reuse detection, httpOnly, revocation |
| V4 Access control | ✅ | Phase 8 |
| V5 Validation and encoding | ✅ | Pydantic at the boundary; `defusedxml`; parameterised SQL |
| V7 Error handling and logging | ✅ | Chained audit log, generic client errors |
| V8 Data protection | 🟡 | Masking, watermarking, download control done; **TDE is an operator step** |
| V9 Communications | ⚙️ | TLS enforced by configuration and by the gateway |
| V10 Malicious code | ⚙️ | ClamAV on upload |
| V11 Business logic | ✅ | Lifecycle machine, approval gates, SoD |
| V12 Files and resources | 🟡 | Size caps, type handling, AV. **No content-type sniffing beyond extension** |
| V13 API | ✅ | Consistent authn/authz across REST and the SOAP facade |
| V14 Configuration | ✅ | Production tripwire, secrets never in code, gitleaks in CI |

## DAST — running in CI

`ci.yml` runs a **ZAP baseline scan** against a live instance on every push, and the `gate` job
depends on it. The API is started with migrations applied and the scan waits on
`/healthz/ready`, not `/health` — scanning a half-migrated app produces findings about a state
that never reaches production.

**The tuning is `.zap/rules.tsv`, and it is the important part of this job.** Every rule that
does not fail the build is listed there with the reason it does not: cache-control on public
endpoints, a `Permissions-Policy` header that is set at the edge and therefore invisible to a
scan pointed at the container, `Sec-Fetch-*` headers that are a client property a server cannot
emit. Anything *not* in that file fails the build.

That is the whole design. The original objection to adding this job was correct — an untuned
DAST job produces a wall of false positives on its first run and gets disabled within a week —
but the answer to it is a triaged rule file, not a permanently deferred job. Lowering the
threshold until nothing fires would have produced a green badge and no signal.

**Honest limits of a baseline scan:**

- It is **passive**. It does not attack: no injection payloads, no fuzzing, no authenticated
  crawl. It finds missing headers, information disclosure and TLS/cookie misconfiguration.
- It runs **unauthenticated**, so the authorisation logic — which is where the interesting bugs
  in a multi-tenant system live — is out of its reach. That surface is covered by the tests
  (tenant isolation, RLS, SoD, need-to-know), not by this.
- A full active scan and an authenticated crawl belong in a scheduled pipeline against a
  staging instance, not on every push; they take too long and their findings need a human.

So: **SAST, dependency, container and secret scanning are enforced on every push, and DAST is
now enforced alongside them at baseline depth.** Penetration testing by a qualified third party
remains a separate, necessary exercise — an automated baseline scan is not one, and nothing here
should be read as claiming otherwise.
