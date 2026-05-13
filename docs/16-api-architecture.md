# 16 — API Architecture

API-first. The same REST API powers the web app, the mobile PWA, integrations, and customers' own automations. FastAPI auto-generates the OpenAPI spec; the frontend's typed client and mock server are generated from it, so FE/BE never drift.

---

## 1. Principles

- **Resource-oriented REST** over HTTPS; JSON in/out; nouns (plural), standard verbs (`GET/POST/PATCH/DELETE`), sub-resources nested where there's a real containment relationship, "actions" as `POST /…/{id}/{action}` when a verb doesn't fit a CRUD shape (`/contracts/{id}/submit`, `/contracts/{id}/sign`, `/envelopes/{id}/send`, `/workflows/{id}/simulate`).
- **Versioned** under `/api/v1/…`; breaking changes → `/api/v2`; non-breaking additions are fine within a version; deprecations carry a `Sunset` header + a documented timeline + a changelog.
- **Tenant scoping is implicit** — the tenant comes from the JWT (and/or the subdomain/host); resource URLs don't repeat it. Cross-tenant access is impossible by construction (RLS + repo filter).
- **Stateless** — bearer JWT access token on every request; no server-side session needed for the API; the web app additionally uses an httpOnly refresh-token cookie for silent renewal.
- **Consistent envelopes** for lists (data + pagination), errors (RFC-7807 problem+json), and async operations (a job resource + `202 Accepted` + `Location`).
- **Idempotent** mutations support an `Idempotency-Key` header. **Optimistic concurrency** via `If-Match: <etag/version>` on updates → `412 Precondition Failed` on conflict.
- **Discoverable & documented** — OpenAPI 3.1 at `/api/v1/openapi.json`, a browsable reference + playground (Scalar/Redoc/Swagger UI), code samples, and a "getting started" guide; webhooks documented as an AsyncAPI-style section.

---

## 2. Auth

- `POST /api/v1/auth/login` → `{ access_token, expires_in, refresh_token? }` (refresh token set as an httpOnly, Secure, SameSite cookie for browser clients; returned in body for trusted server-to-server clients) — or, if MFA is required, `{ mfa_required: true, mfa_token }` → `POST /api/v1/auth/mfa/verify { mfa_token, code, factor }` → tokens.
- `POST /api/v1/auth/refresh` (uses the refresh cookie / body token; **rotates** it; **reuse detection** → if an already-used refresh token is presented, the whole session chain is revoked and the user must re-authenticate).
- `POST /api/v1/auth/logout` (revokes the current refresh token + session). `GET /api/v1/auth/me` (current user, tenant, role, permissions, feature flags). SSO: `GET /api/v1/auth/sso/{provider}/start` → IdP → `GET /api/v1/auth/sso/{provider}/callback` → tokens. SCIM: `/scim/v2/Users`, `/scim/v2/Groups` (bearer-token, IdP-driven provisioning). API tokens (for integrations): issued in settings, scoped + expiring, presented as `Authorization: Bearer <token>`; rate-limited and audited like user requests.
- **Access token**: short-lived (e.g., 15 min) JWT, claims = `sub` (user id), `tid` (tenant id), `role`, `scopes`, `exp`, `iat`, `jti`; signed with a rotating key (JWKS endpoint); never holds secrets or PII beyond ids.
- **Step-up auth**: sensitive endpoints (export audit, change roles, disable MFA, delete workspace, manage API keys, high-assurance signing) require a recent re-auth — the request needs an `X-Step-Up-Token` (obtained via `POST /api/v1/auth/step-up { password|otp }`), short-lived; missing/expired → `403` with `error: "step_up_required"`.

---

## 3. Resource map (selected — all under `/api/v1`)

```
# Identity & tenancy
GET    /me                                  PATCH /me
GET    /tenant   PATCH /tenant               GET  /tenant/branding  PATCH /tenant/branding
GET    /users    POST /users (invite)        GET  /users/{id}  PATCH  DELETE (deactivate)
POST   /users/{id}/reactivate                POST /users/{id}/reset-password  POST /users/{id}/sign-out-all
GET    /roles    POST /roles  GET/PATCH/DELETE /roles/{id}    GET /permissions
GET    /teams    POST /teams  GET/PATCH/DELETE /teams/{id}
GET    /sessions  DELETE /sessions/{id}  DELETE /sessions (all)   GET /devices
GET    /settings/security  PATCH …    GET /settings/sso  PUT …    GET/POST /api-tokens  DELETE /api-tokens/{id}
GET/POST /webhook-endpoints  GET/PATCH/DELETE /webhook-endpoints/{id}   GET /webhook-deliveries  POST /webhook-deliveries/{id}/replay
GET/POST /custom-fields  GET/PATCH/DELETE /custom-fields/{id}
GET    /billing/plan  POST /billing/plan (change)  GET /billing/usage  GET /billing/invoices  PUT /billing/payment-method

# Contracts
GET    /contracts?status=&owner=&type=&tag=&q=&after=&limit=&sort=    POST /contracts
GET    /contracts/{id}   PATCH /contracts/{id}   DELETE /contracts/{id}   POST /contracts/{id}/restore  /archive  /unarchive
POST   /contracts/{id}/duplicate
GET    /contracts/{id}/document   PUT /contracts/{id}/document (save a new version)   GET /contracts/{id}/document/render?format=pdf|docx
GET    /contracts/{id}/versions   GET /contracts/{id}/versions/{vid}   POST /contracts/{id}/versions/{vid}/restore   GET /contracts/{id}/versions/compare?a=&b=
GET/POST /contracts/{id}/parties  GET/PATCH/DELETE /contracts/{id}/parties/{pid}
GET/POST /contracts/{id}/attachments  DELETE …/{aid}
GET/POST /contracts/{id}/obligations  GET/PATCH/DELETE …/{oid}
GET/POST /contracts/{id}/comments  GET/PATCH/DELETE …/{cid}  POST …/{cid}/resolve
GET/POST /contracts/{id}/suggestions  POST …/{sid}/accept  POST …/{sid}/reject
GET    /contracts/{id}/activity   GET /contracts/{id}/access   POST /contracts/{id}/access (share grant)  DELETE /contracts/{id}/access/{gid}
POST   /contracts/{id}/submit          # → enters workflow
POST   /contracts/{id}/withdraw        # pull back from review
GET    /contracts/{id}/approvals       # the workflow run timeline (read)
POST   /contracts/{id}/approvals/decide { decision: approve|reject|request_changes, comment }
POST   /contracts/{id}/approvals/remind  /reassign  /escalate  /skip-step  /change-workflow   # owner/admin, audited
POST   /contracts/{id}/renew           # → renewal wizard data; creates the renewal draft
POST   /contracts/{id}/terminate
GET    /contracts/{id}/insights        POST /contracts/{id}/insights/refresh        # AI analysis
GET    /contracts/{id}/insights/risks  POST /contracts/{id}/insights/risks/{rid}/accept  /request-change

# Templates & clauses
GET/POST /templates  GET/PATCH/DELETE /templates/{id}  POST /templates/{id}/publish  /archive
GET/PUT  /templates/{id}/document   GET/POST /templates/{id}/variables  GET/POST /templates/{id}/default-clauses
GET /templates/{id}/versions  …compare/restore
GET/POST /clauses    GET/PATCH/DELETE /clauses/{id}  POST /clauses/{id}/approve  /deprecate
GET /clauses/{id}/versions   GET/POST /clauses/{id}/fallbacks

# Workflows
GET/POST /workflows  GET/PATCH/DELETE /workflows/{id}  POST /workflows/{id}/activate  /archive
GET/PUT  /workflows/{id}/graph    POST /workflows/{id}/simulate { sample_contract }
GET /workflows/{id}/versions      GET /workflows/{id}/runs   GET /workflows/{id}/runs/{runId}
GET /workflows/{id}/analytics?from=&to=

# Signatures
POST   /contracts/{id}/envelopes                # create a draft envelope (signature prep)
GET/PATCH /envelopes/{id}                       # message, order, expiry, reminders
GET/POST /envelopes/{id}/recipients  GET/PATCH/DELETE …/{rid}
GET/POST /envelopes/{id}/fields      GET/PATCH/DELETE …/{fid}     PUT /envelopes/{id}/fields (bulk place)
POST   /envelopes/{id}/send          POST /envelopes/{id}/resend   POST /envelopes/{id}/void   POST /envelopes/{id}/recipients/{rid}/remind
GET    /envelopes/{id}/certificate   GET /envelopes/{id}/sealed-pdf
# Signing ceremony (token-auth, no account) — the external portal
GET    /sign/{token}                 # envelope+recipient state for this token
POST   /sign/{token}/verify { code }                 POST /sign/{token}/consent
GET    /sign/{token}/document         POST /sign/{token}/fields { fieldId: value, … }
POST   /sign/{token}/adopt-signature { type: typed|drawn|uploaded, data }
POST   /sign/{token}/finish           POST /sign/{token}/decline { reason }
GET    /sign/{token}/download         # the copy they signed / the executed copy when ready
# (and /portal/{token} for view/comment-only external collaboration grants)

# Intelligence (OCR & AI)
POST   /ocr/uploads                  # → presigned S3 URLs for each file
POST   /ocr/jobs { files:[fileIds], options, post_action, default_metadata }   # → 202 + job
GET    /ocr/jobs/{id}                GET /ocr/jobs/{id}/files/{fid}/pages/{pno}     POST /ocr/jobs/{id}/cancel
POST   /ocr/jobs/{id}/files/{fid}/pages/{pno}/rerun   POST /ocr/jobs/{id}/rerun
GET    /ocr/jobs/{id}/extraction     PATCH /ocr/jobs/{id}/extraction      # human corrections
POST   /ocr/jobs/{id}/create-contract { fileId|merged, verifiedValues }
POST   /ai/assistant/messages { context:{type,id}, message }       GET /ai/assistant/messages?context=…
POST   /ai/draft { kind, target, instruction }     POST /ai/translate { text, to }     POST /ai/summarize { contractId, length, lang }
POST   /search { query }              # NL → {interpreted_filters, results[]}     GET /search?…structured…

# Cross-cutting
GET    /dashboard?from=&to=&department=          # the widgets' payloads
GET    /reports/{key}?…filters…                  GET/POST /reports/builder  GET/PATCH/DELETE /reports/builder/{id}  POST …/{id}/schedule  POST …/{id}/run
GET    /audit?actor=&action=&object=&from=&to=&after=&limit=     POST /audit/export { filters } → 202 + job
GET    /notifications?unread=&type=&after=        POST /notifications/{id}/read  POST /notifications/read-all  POST /notifications/{id}/snooze  POST /notifications/mute
GET    /inbox/approvals   GET /inbox/signatures
GET    /jobs/{id}         GET /jobs?status=&type=                # the Progress Tray
GET    /files/{id}        GET /files/{id}/download               # → 302 to a short-lived presigned URL
POST   /uploads           # generic presigned-URL minting for attachments/avatars/logos
GET    /health  GET /ready                                       # probes (unauthenticated, minimal)
```

---

## 4. Conventions in detail

- **Pagination** (lists): cursor-based — `?after=<opaque-cursor>&limit=<n≤200>` → response `{ "data": [...], "page": { "next": "<cursor|null>", "limit": n } }`; some lists also support `?before=` for backward paging; total counts are returned only when cheap (small tables) else estimated or omitted (`page.estimated_total`).
- **Filtering/sorting**: query params named after fields (`?status=in_review&owner=<id>&type=msa&tag=renewal&end_before=2026-12-31`); arrays as repeated params or comma-lists; `?q=` for full-text; `?sort=-updated_at` (prefix `-` = desc, comma for multi-key); `?include=` to expand related resources (`?include=owner,parties` — sparse-by-default to keep payloads small); `?fields=` to project specific fields.
- **Errors** (RFC 7807 `application/problem+json`): `{ "type": "https://docs.…/errors/quota-exceeded", "title": "OCR page quota exceeded", "status": 402, "detail": "You've used 5,000 of 5,000 pages this period.", "code": "quota_exceeded", "instance": "/api/v1/ocr/jobs", "request_id": "req_…", "errors": [ { "field": "files", "code": "too_many", "message": "Max 200 files per batch." } ] }`. Stable machine `code`s; field-level `errors` for validation (422); `request_id` always present (echoes `X-Request-Id` or generates one) — what a user gives support; never a stack trace.
- **Status codes**: `200` ok, `201` created (with `Location`), `202` accepted (async — body is a `job` resource; `Location: /jobs/{id}`), `204` no content, `400` malformed, `401` unauthenticated, `403` forbidden / `step_up_required`, `404` not found (also returned instead of `403` where leaking existence is undesirable), `409` conflict (state-machine violation, duplicate), `412` precondition failed (stale `If-Match`), `422` validation, `429` rate-limited (with `Retry-After`), `5xx` server.
- **Async operations**: any operation that may take >~2s returns `202` + a `job` resource (`{ id, type, status, progress, items, result_ref, ... }`); poll `GET /jobs/{id}` or subscribe (below); on completion `result_ref` points at the created resource(s); the same `job` powers the Progress Tray. Examples: OCR jobs, bulk import, PDF render, mass-send, audit export, report generation.
- **Real-time**: a WebSocket (or SSE) channel `GET /api/v1/stream` (authenticated) delivers: job progress, new notifications, presence/edit events for documents the user is viewing, workflow-run updates, and "live" dashboard nudges — so the UI doesn't poll. Per-tenant, per-user scoped; falls back to polling if WS is blocked. The collaborative editor uses a separate WS/CRDT endpoint (`/collab/{contractId}`) on the collab service (Doc 11/18).
- **Idempotency**: `Idempotency-Key: <uuid>` on `POST`s that create/charge/send → the result is stored and replays return it (within a TTL); without the header, retries may duplicate (caller's risk).
- **Rate limiting**: per-token and per-tenant token-bucket limits (different tiers for interactive vs API-token traffic, lower for unauthenticated endpoints like `/sign/{token}` per-IP); `X-RateLimit-Limit/Remaining/Reset` headers; `429` + `Retry-After` on breach; abusive patterns escalate (temporary block + alert).
- **Webhooks (outbound)**: tenants register endpoints + select event types; we POST `{ id, type, created_at, tenant_id, data }` signed with an HMAC-SHA256 over the body using the endpoint secret (`X-CM-Signature: t=…,v1=…` — timestamped to prevent replay); deliveries retried with backoff (then dead-lettered + alert); a delivery log with replay; events match the domain events (Doc 14 §6) — `contract.created/submitted/approved/rejected/signed/activated/expiring/renewed/terminated`, `envelope.sent/completed/declined`, `ocr.completed`, `ai.analysis.completed`, `workflow.run.advanced`, `risk.flagged`, `obligation.due`, `user.invited`, etc.
- **CORS & security headers**: tight CORS allowlist (the app's origins + tenant custom domains); `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` on all responses; cookies `HttpOnly; Secure; SameSite=Lax` (refresh) / strict where possible.
- **i18n**: `Accept-Language` (and the user's stored preference) selects the language for human-readable strings in responses (error `detail`s, generated content); resource *data* (contract content) is in its own language regardless.
- **Pagination/payload caps**: max `limit`, max request body size (esp. for `document` PUTs), max batch sizes (200 files, N recipients) — all enforced with clear `422`s.
- **Deprecation policy**: a public changelog; `Sunset` + `Deprecation` headers on endpoints/fields being retired; minimum N-month notice; never break `/api/v1` — breaking changes get `/api/v2` with a migration guide and an overlap window.

---

## 5. The generated client & contract testing

FastAPI emits OpenAPI 3.1 → the frontend generates a fully-typed TS client (`openapi-typescript` + a thin fetch wrapper, or `orval`/`hey-api`) and **MSW mock handlers** from the same spec, so: (1) the FE compiles against the real API shape; (2) FE devs work against realistic mocks before the BE endpoint exists; (3) a CI check fails if the spec changes incompatibly; (4) the public docs and the playground are generated from the spec too. Backend has API contract tests asserting the spec is honored. Integrations get the same OpenAPI + SDKs (TS + Python at minimum) + Postman collection.
