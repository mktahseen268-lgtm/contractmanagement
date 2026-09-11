from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_SECRET_KEY = "dev-only-change-me-please-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Contract Management API"
    env: Literal["dev", "test", "uat", "staging", "production"] = "dev"

    # --- Deployment profile (Phase 0) ---
    # `saas`          — the original multi-tenant product: registration is open, a tenant is
    #                   created per signup, and DB-level isolation is mandatory.
    # `single_tenant` — the MMBL on-prem profile: exactly one tenant is provisioned at install,
    #                   registration is disabled, and the tenant-switching UI is hidden. The
    #                   code path does NOT fork — `get_current_user` still sets the tenant
    #                   ContextVar and repositories still filter by `tenant_id`.
    deployment_mode: Literal["saas", "single_tenant"] = "saas"
    single_tenant_id: str = ""        # resolved at startup when empty (the sole tenant row)
    single_tenant_name: str = "Organisation"
    #: Governing law written onto every new agreement. The drafting screen no longer asks:
    #: this installation serves one bank in one jurisdiction, and a free-text box invited a
    #: typo on a field that decides which courts hear a dispute.
    default_governing_law: str = "Islamic Republic of Pakistan"
    single_tenant_slug: str = "org"
    # DB-level row security. Mandatory for saas. Optional for single_tenant, where one tenant
    # makes the policy a tautology and Oracle VPD / MSSQL security policies cost real latency.
    enforce_db_isolation: bool = True

    # --- Database. PostgreSQL, MSSQL and Oracle are production targets; SQLite is dev-only. ---
    database_url: str = "postgresql+psycopg2://cm:cm@localhost:5432/cm"

    # --- Auth / JWT ---
    secret_key: str = _DEV_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30          # short-lived; refreshed via the rotating refresh cookie
    refresh_token_expire_days: int = 14            # opaque server-side token (rotated on use)
    mfa_token_expire_minutes: int = 5              # the short token between the password step and the 2FA step
    otp_expire_minutes: int = 10                   # email OTP validity
    otp_max_attempts: int = 5

    # --- Refresh cookie ---
    refresh_cookie_name: str = "cm_refresh"
    cookie_secure: bool = False                    # MUST be true in prod (https); false for local http
    cookie_samesite: str = "lax"                   # lax | strict | none

    # --- Login lockout (RFI §A.7) ---
    login_max_failures: int = 5                    # consecutive failures before lockout
    login_failure_window_minutes: int = 10         # rolling window the failures are counted in
    login_lockout_minutes: int = 15                # how long the user stays locked out

    # --- Encryption-at-rest for sensitive columns (MFA secret + signing-link secret +
    # webhook HMAC secret). Same key chain so one rotation rotates everything. ---
    # Newline-separated Fernet keys; the first is the current encryption key, the rest are kept
    # for read-side rotation. Empty in dev — the EncryptedString type then passes values through.
    mfa_encryption_keys: str = ""

    # --- Audit-log tamper-evidence chain (RFI §A.16 / docs/19) ---
    # HMAC key for the per-tenant hash chain on `audit_log`. Defaults to deriving from
    # `secret_key` when empty (still useful — every row is HMAC'd; an attacker needs *both*
    # the DB and this key to forge a consistent chain). In production set explicitly so JWT
    # signing-key rotation doesn't invalidate historical verification.
    audit_chain_key: str = ""

    # --- Password policy (RFI §A.7) ---
    password_min_length: int = 12                  # production minimum; dev override below
    password_min_length_dev: int = 8               # used when env=dev for ergonomics
    password_require_classes: int = 3              # require >= N of {lower, upper, digit, symbol}
    password_max_length: int = 128                 # bcrypt truncates at 72 bytes anyway; cap at 128

    # --- Signing-link tokens ---
    signing_token_ttl_days: int = 14               # expiry for /sign/{token} URLs

    # --- Rate limit (RFI §A.7) ---
    rate_limit_enabled: bool = True
    rate_limit_store: Literal["memory", "redis"] = "memory"  # redis recommended in prod
    rate_limit_redis_url: str = ""                 # falls back to `redis_url` when empty

    # --- Security headers (CSP can be loosened via env if frontend hosts elsewhere) ---
    security_headers_enabled: bool = True
    csp_extra_connect: str = ""                    # extra `connect-src` origins (comma-separated)
    csp_report_only: bool = False

    # --- Logging ---
    log_format: Literal["json", "text"] = "json"   # text in dev for human readability, json in prod
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- SSO / OIDC (RFI T-3 / docs/19). Off by default (password auth). When enabled, users
    # can sign in via any OIDC IdP (Okta / Entra / Google / Keycloak). New SSO users are
    # JIT-provisioned into `oidc_default_tenant_id` (or matched to an existing user by email). ---
    oidc_enabled: bool = False
    oidc_issuer: str = ""                          # e.g. https://accounts.google.com
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_url: str = ""                    # https://api.example.com/auth/sso/callback
    oidc_scopes: str = "openid email profile"
    oidc_default_tenant_id: str = ""               # workspace new SSO users land in
    oidc_default_role: str = "author"

    # --- SCIM 2.0 provisioning (RFI T-3). An IdP creates/deactivates users via /scim/v2/Users,
    # --- FIDO2 / WebAuthn (Phase 8, item 1). The only factor here that resists phishing: a
    # passkey is bound to the origin it was registered against and will not respond to a
    # lookalike domain. `webauthn_rp_id` MUST be the registrable domain the app is served
    # from — a mismatch makes every credential silently unusable. ---
    webauthn_enabled: bool = False
    #: e.g. "cm.mmbl.test" — no scheme, no port.
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "Contract Management"
    #: Full origin including scheme, e.g. "https://cm.mmbl.test". Defaults to https + rp_id.
    webauthn_origin: str = ""

    # --- Antivirus on upload (Phase 8, item 7). ClamAV over INSTREAM, on-prem. When enabled
    # but unreachable this FAILS CLOSED — the opposite of every other integration here, and
    # deliberately: an antivirus that waves files through when it cannot reach the daemon
    # provides no protection at exactly the moment an attacker would choose. ---
    clamav_enabled: bool = False
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_timeout: int = 30

    # --- SOAP facade (Phase 7, item 9) for legacy core-banking integration. Off by default:
    # an unused SOAP endpoint is attack surface with no user. It is a facade over the same
    # service functions the REST routes call, authenticated with the same API keys. ---
    soap_enabled: bool = False

    # --- Outbound connectors (Phase 7, items 4 and 5). All optional; a connector that is
    # unreachable must never break the work it is reporting on. Every destination goes through
    # the residency allowlist. Calendar invites need no configuration at all — they are .ics
    # attachments on mail we already send. ---
    teams_enabled: bool = False
    #: Teams incoming-webhook URL for the channel to post into.
    teams_webhook_url: str = ""
    sharepoint_enabled: bool = False
    #: On-prem SharePoint Server or SharePoint Online — the RFP forbids the data leaving the
    #: deployment, so which one is the operator's decision and the residency gate enforces it.
    sharepoint_site_url: str = ""
    sharepoint_library: str = "Shared Documents/Contracts"
    sharepoint_token: str = ""

    # --- SIEM feed (Phase 7, item 2). Security events projected from the audit log and
    # shipped over syslog to an on-prem collector. Off by default; the endpoint goes through
    # the same residency allowlist as every other egress. Delivery is best-effort and never
    # blocks a request — a collector outage must not stop people signing contracts. ---
    siem_enabled: bool = False
    siem_host: str = ""
    siem_port: int = 6514
    siem_tls: bool = True
    #: Only ever turned off deliberately. An unverified TLS channel to a log collector is one
    #: an attacker can stand in the middle of.
    siem_verify: bool = True
    siem_ca_path: str = ""
    siem_timeout: int = 5
    #: cef | clf
    siem_format: str = "cef"
    #: Overrides the hostname in the syslog header; useful behind a NAT where gethostname()
    #: returns something the collector cannot correlate.
    siem_hostname: str = ""

    # --- SAML 2.0 (T-3, the other half of SSO). For IdPs that do not speak OIDC — Entra ID
    # in MMBL's case. Disabled until the operator supplies the IdP's SSO URL and signing
    # certificate; every SAML endpoint 404s until then, so a half-configured deployment does
    # not advertise an ACS URL that cannot work. ---
    saml_enabled: bool = False
    #: Where to send the user to authenticate (IdP HTTP-Redirect SSO endpoint).
    saml_idp_sso_url: str = ""
    #: IdP single-logout endpoint. Optional — without it, logout is local only.
    saml_idp_slo_url: str = ""
    #: The IdP's signing certificate. PEM or a bare base64 blob; both are accepted because
    #: IdP consoles hand it out both ways.
    saml_idp_certificate: str = ""
    #: Our own entity ID. Defaults to the metadata URL, which is the usual convention.
    saml_sp_entity_id: str = ""
    #: Public base URL of this API, used to build ACS/SLO/metadata URLs.
    saml_sp_base_url: str = ""
    #: Workspace SAML users are provisioned into.
    saml_default_tenant_id: str = ""
    saml_default_role: str = "author"
    #: {IdP group name or object id: workspace role}. Which AD group means "manager" is a
    #: fact about the customer's directory, so it is configuration rather than code.
    saml_group_role_map: dict = {}

    # authenticated with `scim_token`, provisioning into `scim_tenant_id`. ---
    scim_enabled: bool = False
    scim_token: str = ""
    scim_tenant_id: str = ""

    # --- Observability (RFI T-1 / docs/26) ---
    # `/metrics` (Prometheus) is always on. OpenTelemetry tracing is opt-in: set otel_enabled
    # AND point otel_exporter_otlp_endpoint at a collector (OTLP/HTTP, e.g. http://otel:4318).
    # Requires the optional extras in `requirements-otel.txt`; degrades to a no-op otherwise.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""          # e.g. http://otel-collector:4318
    otel_service_name: str = "cm-api"

    # --- PKI (Phase 1 / RFP §4a "PKI Depth & Advanced eSignature", docs/PKI-ARCHITECTURE.md) ---
    # Key custody. `soft` = keys encrypted at rest with the Fernet chain (dev/CI — honest, but
    # not FIPS). `pkcs11` = keys generated inside and confined to an HSM; needs
    # requirements-pki.txt plus the HSM_* settings below. Production must use pkcs11.
    keystore_provider: Literal["soft", "pkcs11"] = "soft"
    hsm_library_path: str = ""        # e.g. /usr/lib/softhsm/libsofthsm2.so
    hsm_slot: int = 0
    hsm_token_label: str = ""         # preferred over hsm_slot when set (slots renumber)
    hsm_pin: str = ""                 # from env or a secret store — never a file in the repo

    # CA hierarchy. The root is generated once and taken offline; the issuing CA signs
    # day-to-day certificates. Validity is deliberately long for the root and short for
    # end-entity certificates.
    pki_root_cn: str = "Contract Management Root CA"
    pki_issuing_cn: str = "Contract Management Issuing CA"
    pki_org: str = "Contract Management"
    pki_country: str = "PK"
    pki_root_key_algorithm: str = "ec-p384"
    pki_issuing_key_algorithm: str = "ec-p384"
    pki_leaf_key_algorithm: str = "ec-p256"
    pki_root_validity_years: int = 20
    pki_issuing_validity_years: int = 10
    pki_leaf_validity_days: int = 730        # internal signatories (2 years)
    pki_visitor_validity_days: int = 7       # external one-off signatories (Phase 2)

    # Published distribution points, embedded as CRLDistributionPoints / AIA in every
    # issued certificate. Must be reachable by relying parties inside the deployment.
    pki_base_url: str = ""                   # e.g. https://cm.mmbl.internal — falls back to frontend_url
    crl_validity_hours: int = 24             # nextUpdate on a full CRL
    crl_delta_validity_hours: int = 1        # nextUpdate on a delta CRL

    # Registration Authority. With dual control on, two *different* RA officers must approve
    # before a certificate is issued (RFP §4a — RA workflow tied to HR/identity).
    ra_dual_control: bool = False
    # Revocation checking when validating third-party certificates.
    pki_revocation_check: Literal["off", "soft_fail", "hard_fail"] = "soft_fail"

    # --- Workflow engine + SLA clock (Phase 4 / RFI §3) ---
    # An SLA in wall-clock hours is wrong for a bank: a review raised at 16:00 on a Friday is
    # not overdue on Saturday. These define the business calendar the SLA clock runs on;
    # public holidays are per-tenant rows in `holidays`.
    business_working_days: str = "0,1,2,3,4"   # date.weekday(): Mon=0 … Sun=6
    business_day_start_hour: int = 9
    business_day_end_hour: int = 18
    #: Remind the assignee once this fraction of the SLA has elapsed.
    sla_reminder_fraction: float = 0.75
    #: How often the sweep runs (seconds). Reminders and escalations are only as timely as this.
    sla_sweep_seconds: float = 900.0
    #: Escalate automatically when a step passes its due time. Off means "flag it, do not
    #: reassign" — some banks want a human to decide before authority moves.
    sla_auto_escalate: bool = True

    # --- SMS (Phase 2 — OTP for the visitor eSigning surface) ---
    # `console` logs (dev/CI), `http` posts to a generic gateway (what the Pakistani
    # aggregators expose), `null` accepts and drops (load testing).
    sms_backend: Literal["console", "http", "null"] = "console"
    sms_http_url: str = ""
    sms_http_method: str = "POST"
    #: `{to}` and `{text}` are substituted. JSON body if it parses as JSON, else form-encoded.
    sms_http_body_template: str = ""
    sms_http_auth_header: str = ""       # e.g. Authorization
    sms_http_auth_value: str = ""        # e.g. Bearer xxx — from a secret store
    sms_sender_id: str = "MMBL"

    # --- Visitor eSigning surface (Phase 2 / RFP §4a) ---
    # External signatories sign without any account. Sized for 100,000 signatories/year.
    esign_enabled: bool = True
    esign_otp_length: int = 6
    esign_otp_ttl_minutes: int = 10
    esign_otp_max_attempts: int = 5          # wrong codes before the session is blocked
    esign_otp_max_sends: int = 3             # resends per session
    #: Sessions started per invitation per hour, per IP. The first line against bulk
    #: automation; the Redis rate limiter and an edge WAF are the other two.
    esign_sessions_per_hour: int = 20
    #: Require the viewer to reach the end of the document before the sign button unlocks.
    #: This is consent evidence, not decoration — it is printed on the Certificate.
    esign_require_scroll: bool = True
    #: Proof-of-work difficulty for starting a session (0 disables). Dependency-free and
    #: self-hosted, unlike a CAPTCHA SaaS, which the residency rule forbids at runtime.
    esign_pow_bits: int = 12
    esign_invitation_ttl_days: int = 90

    # --- Data residency (Phase 0 / RFP "Hosting & data residency statement") ---
    # The deployment must keep contract content, signatory PII, key material and audit logs
    # inside the country of operation. We do not geo-locate at runtime — that would itself be
    # a call to a foreign service. Instead every configured egress endpoint (object storage,
    # SMTP, OCR, OTel collector) must resolve to a private/loopback address or appear in
    # `data_residency_allow_hosts`. Startup refuses to boot otherwise.
    data_residency_region: str = "PK"
    data_residency_enforced: bool = True
    data_residency_allow_hosts: str = ""           # comma-separated extra hostnames/IPs/CIDRs

    # --- Contract archive + purge (Phase 0 item 7 / RFP "10 years, 1 year instantly searchable") ---
    retention_years: int = 10                      # hard-purge horizon for executed contracts
    hot_search_years: int = 1                      # stays in the live search index this long
    archive_storage_prefix: str = "archive"        # cold-tier key prefix inside the bucket
    archive_s3_storage_class: str = ""             # e.g. GLACIER / STANDARD_IA; empty = same tier

    # --- Retention policy (RFI §C.8-C.11) ---
    retention_audit_hot_days: int = 365            # 1 year in DB
    retention_audit_archive_days: int = 3650       # 10 years total
    retention_webhook_delivery_days: int = 90
    retention_background_job_days: int = 90
    retention_email_outbox_days: int = 30

    # --- Email (for OTP / notifications). console = log it (dev); smtp = real send. ---
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "no-reply@contract-management.local"
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    # Implicit-SSL mode (SMTPS, typically port 465). When true, uses smtplib.SMTP_SSL and
    # skips STARTTLS. Use this for hosts like Hostinger/cPanel mailservers that listen 465 only.
    smtp_ssl: bool = False

    # --- CORS (frontend origins, comma-separated) ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # public URL of the frontend (used in emails — e.g. signing links)
    frontend_url: str = "http://localhost:3000"

    # --- Startup behaviour ---
    run_migrations_on_startup: bool = True
    auto_seed: bool = True

    # --- Background jobs (Celery + Redis) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""                     # empty -> falls back to redis_url
    celery_result_backend: str = ""
    celery_task_always_eager: bool = True

    # --- OCR / AI extraction (RFI T-5 / docs/09). `stub` = deterministic demo (no document
    # read); `anthropic` = real extraction via Claude (needs ocr_api_key + the `anthropic`
    # package from requirements-ai.txt). Falls back to stub when not fully configured. ---
    # `local` is the MMBL setting: an OpenAI-compatible model served *inside* the deployment
    # (vLLM, Ollama, LM Studio, …). No document ever leaves the network, which the residency
    # rule requires — the hosted adapter is for deployments without that constraint.
    ocr_provider: Literal["stub", "anthropic", "local"] = "stub"
    ocr_api_key: str = ""
    ocr_model: str = "claude-haiku-4-5-20251001"
    ocr_max_pages: int = 20
    #: Base URL of the on-prem OpenAI-compatible endpoint, e.g. http://llm.internal:8000/v1
    ocr_base_url: str = ""

    # --- Writing assistant (text correction). Off unless a model is reachable inside the
    # --- deployment. There is deliberately no hosted option: assistance runs over draft
    # --- contract text, so a foreign endpoint would contradict the residency commitment.
    #: builtin = deterministic spelling and punctuation checks, no model required (the
    #: default). local = an OpenAI-compatible model inside your network, which adds
    #: rephrasing. none = switch the feature off entirely.
    text_assist_provider: Literal["builtin", "local", "none"] = "builtin"
    #: An OpenAI-compatible base URL on the bank's own hardware, e.g. http://llm.internal/v1
    text_assist_base_url: str = ""
    text_assist_model: str = ""
    text_assist_api_key: str = ""
    #: Interactive, so the timeout is short. A writing aid that hangs is worse than none.
    text_assist_timeout_seconds: int = 30
    #: Per-request cap. Assistance is for a passage, not a whole agreement body.
    text_assist_max_chars: int = 8000

    # --- Cryptographic document seal on the executed PDF (RFI T-4 / docs/19). `internal` =
    # visual evidence only (default); `pades` = real PAdES signature via pyhanko + a PKCS#12
    # cert (+ optional RFC-3161 TSA). Falls back to internal when not fully configured. ---
    # `internal` = visual evidence only. `pades` = ONE shared organisational PKCS#12 seal
    # (kept for deployments with no internal CA — the RFP forbids shared certificates, so this
    # is not the compliant setting). `pki` = per-signatory PAdES-LTV using the in-platform CA
    # from Phase 1: each signatory signs with their own certificate and key. The MMBL profile
    # must use `pki`.
    signing_provider: Literal["internal", "pades", "pki"] = "internal"
    signing_cert_path: str = ""                     # path to a PKCS#12 (.p12/.pfx) cert
    signing_cert_password: str = ""
    signing_field_name: str = "Signature1"
    signing_reason: str = "Executed via Contract Management"
    signing_tsa_url: str = ""                        # RFC-3161 timestamp authority (optional)

    # --- Object storage (S3-compatible). Empty s3_bucket -> local-filesystem fallback. ---
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    # Per-object server-side encryption — empty disables (e.g. for MinIO without KMS in dev).
    # "AES256" = SSE-S3 (default AWS-managed key). "aws:kms" = SSE-KMS (requires `s3_sse_kms_key_id`).
    s3_sse: Literal["", "AES256", "aws:kms"] = ""
    s3_sse_kms_key_id: str = ""
    local_storage_dir: str = "./storage"
    max_upload_mb: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def csp_extra_connect_list(self) -> list[str]:
        return [o.strip() for o in self.csp_extra_connect.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def db_dialect(self) -> str:
        """`postgresql`, `mssql`, `sqlite`, … — first segment of the URL up to `+` or `://`."""
        url = self.database_url.lower()
        # postgresql+psycopg2://…  -> postgresql
        head = url.split("://", 1)[0].split("+", 1)[0]
        return head

    @property
    def is_postgres(self) -> bool:
        return self.db_dialect == "postgresql"

    @property
    def is_mssql(self) -> bool:
        return self.db_dialect == "mssql"

    @property
    def is_sqlite(self) -> bool:
        return self.db_dialect == "sqlite"

    @property
    def is_oracle(self) -> bool:
        return self.db_dialect == "oracle"

    @property
    def is_single_tenant(self) -> bool:
        return self.deployment_mode == "single_tenant"

    @property
    def registration_enabled(self) -> bool:
        """Self-service signup exists only in the SaaS profile — an on-prem bank provisions
        users through SSO/SCIM or an admin, never through a public register form."""
        return not self.is_single_tenant

    @property
    def data_residency_allow_host_list(self) -> list[str]:
        return [h.strip() for h in self.data_residency_allow_hosts.split(",") if h.strip()]

    @property
    def pki_public_base_url(self) -> str:
        """Where relying parties fetch CRLs and reach the OCSP responder. These URLs are baked
        into every issued certificate and cannot be changed retroactively — set
        `PKI_BASE_URL` explicitly before issuing anything in production."""
        return (self.pki_base_url or self.frontend_url).rstrip("/")

    @property
    def use_s3(self) -> bool:
        return bool(self.s3_bucket)

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def is_production(self) -> bool:
        return self.env in ("production", "staging", "uat")

    @property
    def is_non_production(self) -> bool:
        """dev *or* test. The production config tripwire exempts both — `ENV=test` is how the
        pytest harness and CI declare "this is not a deployment", exactly as documented in
        CLAUDE.md. Without this, TestClient could never start the app."""
        return self.env in ("dev", "test")

    @property
    def effective_password_min_length(self) -> int:
        return self.password_min_length_dev if self.is_dev else self.password_min_length

    @property
    def effective_audit_chain_key(self) -> str:
        """Use the explicit `audit_chain_key` when set; otherwise derive a stable key from
        `secret_key` so chaining still works without operator config (with the caveat that a
        rotation of `secret_key` invalidates historical verification)."""
        if self.audit_chain_key:
            return self.audit_chain_key
        return f"audit-chain::{self.secret_key}"

    def validate_for_production(self) -> list[str]:
        """Return a list of fatal misconfigurations when running outside dev. The app raises on
        these at startup so the operator can't accidentally launch with dev defaults."""
        errors: list[str] = []
        if not self.is_non_production:
            if self.secret_key == _DEV_SECRET_KEY:
                errors.append("SECRET_KEY is still the dev default — set a 32+ byte secret from a CSPRNG.")
            if len(self.secret_key) < 32:
                errors.append("SECRET_KEY must be at least 32 bytes.")
            if not self.cookie_secure:
                errors.append("COOKIE_SECURE must be true outside of dev (https).")
            if not self.mfa_encryption_keys:
                errors.append("MFA_ENCRYPTION_KEYS must be set (one or more Fernet keys, newline-separated).")
            if self.cors_origins.startswith("http://localhost") and "localhost" in self.cors_origins:
                errors.append("CORS_ORIGINS still contains localhost — narrow to the real frontend domain(s).")
            if self.is_sqlite:
                errors.append("SQLite is not supported outside dev — switch to PostgreSQL, MSSQL or Oracle.")

        # --- Deployment-profile coherence (Phase 0). Checked in every env, including dev:
        # a SaaS-shaped config in single-tenant mode is a misconfiguration, not a preference.
        if self.is_single_tenant:
            if self.is_sqlite and not self.is_non_production:
                errors.append("DEPLOYMENT_MODE=single_tenant requires PostgreSQL, MSSQL or Oracle — not SQLite.")
            if self.auto_seed and not self.is_non_production:
                errors.append(
                    "AUTO_SEED must be false in a single-tenant deployment — the demo workspace "
                    "would create a second tenant and demo credentials."
                )
            if self.oidc_default_tenant_id and self.single_tenant_id and (
                self.oidc_default_tenant_id != self.single_tenant_id
            ):
                errors.append("OIDC_DEFAULT_TENANT_ID must equal SINGLE_TENANT_ID in single-tenant mode.")
            if self.scim_tenant_id and self.single_tenant_id and self.scim_tenant_id != self.single_tenant_id:
                errors.append("SCIM_TENANT_ID must equal SINGLE_TENANT_ID in single-tenant mode.")
        elif not self.enforce_db_isolation:
            errors.append(
                "ENFORCE_DB_ISOLATION cannot be false in the multi-tenant (saas) profile — "
                "database row-level security is the primary isolation boundary."
            )
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
