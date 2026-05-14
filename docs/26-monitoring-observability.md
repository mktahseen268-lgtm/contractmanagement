# 26 · Monitoring & Observability

The platform emits the three pillars of observability:

1. **Logs** — structured JSON on stdout (CLF-style field names, RFC 5424 severity).
2. **Metrics** — Prometheus exposition format at `/metrics` (planned T-1).
3. **Traces** — OpenTelemetry SDK pre-instrumented (planned T-1) via OTLP/HTTP.

Plus a strong durable **audit log** in the database for compliance reads.

## 1. Logs

### 1.1 Format

```json
{
  "ts":"2026-05-14T10:31:11.143Z",
  "level":"INFO",
  "logger":"http",
  "request_id":"01HQXX0FCY1Q9M5VYP2HHFMN3D",
  "method":"POST",
  "path":"/contracts/abc/transition",
  "status":200,
  "duration_ms":47,
  "client_ip":"203.0.113.42",
  "user_id":"u_…",
  "tenant_id":"t_…",
  "msg":"request"
}
```

Authentication failures emit an additional `level: WARN` entry with `event: auth.login.failed`.
Server errors emit `level: ERROR` with the truncated, **sensitive-data-redacted** traceback.

### 1.2 Sensitive-data redaction

The logging middleware **never** logs:

- Request body or query strings of `/auth/login`, `/auth/mfa/*`, `/auth/otp/send`,
  `/auth/password-change`, `/auth/register`, `/users` (POST), `/api-keys` (POST).
- Header values for `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`,
  `X-CAPTCHA-Token`.
- Anything matching `password`, `secret`, `token`, `mfa_code`, `otp_code`,
  `recovery_code`, `signing_link`, `tab_fills[].value`.

These are redacted to `<redacted>` before the JSON is serialised.

### 1.3 Severity policy

| Event | Level |
|---|---|
| Successful 2xx requests, info events | `INFO` |
| 4xx client errors, auth failures, rate-limited, locked-out | `WARN` |
| 5xx server errors, dependency failures (DB, S3, SMTP), webhook delivery failures | `ERROR` |
| Security-critical: refresh-token-reuse-detected, last-owner-protection-violated, signature seal failure, RLS GUC missing | `CRITICAL` |

### 1.4 Shipping

The container writes to stdout. The runtime ships it forward:

- **k8s** + Splunk OTel Collector / Fluent Bit / Filebeat / Vector — pick one.
- **ECS** + Firelens to Kinesis / OpenSearch.
- **Docker Compose** + `docker logs` for dev.

A Loki + Promtail option is shown in [`infra/loki/`](../infra/loki/).

## 2. Metrics (T-1 — planned, scaffolding in place)

Prometheus client wired at `/metrics`. The exposition will include:

### 2.1 Default exporters

- `http_requests_total{method,path,status}` — counter.
- `http_request_duration_seconds_bucket{...}` — histogram.
- `process_*`, `python_gc_*` — runtime.

### 2.2 Domain counters / gauges

```
cm_contracts_total{status=…}                    gauge
cm_envelopes_total{status=…}                    gauge
cm_jobs_total{type=…,status=…}                  counter
cm_webhook_deliveries_total{status=…}           counter
cm_email_outbox_pending                          gauge
cm_signature_seal_duration_seconds              histogram
cm_renewals_sweep_lastrun_seconds_ago           gauge
cm_login_failures_total{tenant_id=…}            counter
cm_rate_limit_rejections_total{route_class=…}   counter
```

Dashboards as JSON in [`infra/grafana/dashboards/`](../infra/grafana/dashboards/).

### 2.3 Alerts

| Alert | Condition | Severity |
|---|---|---|
| API 5xx surge | `rate(http_requests_total{status=~"5.."}[5m]) > 1` | Warn |
| Auth failures spike | `rate(cm_login_failures_total[5m]) > 30 per tenant` | High |
| Refresh reuse detected | any | Critical (page) |
| DB connection saturation | `pg_stat_activity_count / pg_settings_max_connections > 0.8` | High |
| Outbox backlog | `cm_email_outbox_pending > 100` | Warn |
| Webhook delivery failures | `rate(cm_webhook_deliveries_total{status="failed"}[10m]) > 5` | Warn |
| Renewals sweep stale | `cm_renewals_sweep_lastrun_seconds_ago > 7200` | Warn |
| Seal failure | any | Critical |
| Storage put failures | any | Critical |
| Backup older than 36 h | external check | Critical |
| TLS cert expiring < 14 d | external check | High |

PagerDuty / OpsGenie / Sentinel routing matrix in [`infra/alerts/routing.md`](../infra/alerts/routing.md).

## 3. Traces (T-1 — planned)

OpenTelemetry SDK with auto-instrumentation for FastAPI, SQLAlchemy, Celery, requests, boto3.
Export OTLP/HTTP to an OTel collector. The collector fans out to:
- **Tempo / Jaeger** for traces;
- **Loki** for logs (with shared `trace_id`);
- **Prometheus** for metrics.

Sample trace span IDs are propagated in the JSON access log as `trace_id` / `span_id` so
log-to-trace pivot works in Grafana.

## 4. Audit log (compliance)

The `audit_log` table is the compliance source of truth. UI: `/audit` page (admin / auditor
role can see all; everyone else sees their own actions).

Retention: 1 year hot in DB + 10 years archived to S3 as Parquet (partitioned by tenant +
month), reachable via Athena / Glue / Synapse.

## 5. Synthetic monitoring

- `GET /` (root info) — should return JSON with `version`.
- `GET /health` — liveness; returns `{status:"ok"}`.
- `GET /healthz/ready` — **planned** readiness probe — checks DB + Redis + storage round-trip.
- A `/sign/_synthetic` route can be added behind a feature flag to exercise the public
  signing portal periodically.

External synthetic checks (Pingdom / UptimeRobot / Datadog Synthetics) hit:
- `/health` (60 s) — liveness.
- `/auth/login` with a test account behind a sentinel header (10 min) — end-to-end auth.
- `/contracts` (10 min, with API key) — end-to-end DB read path.

## 6. SLOs (suggested initial targets)

| Endpoint class | SLO | Window |
|---|---|---|
| API availability | 99.9 % | 28-day rolling |
| API p95 latency | < 400 ms | 28-day rolling |
| Web availability | 99.9 % | 28-day rolling |
| Webhook dispatch success | > 99 % | 28-day rolling |
| Renewal sweep on-time (< 65 min since last run) | 99 % | 28-day rolling |
| Background job completion (success) | > 99 % | 28-day rolling |

Error-budget burn alerts on the API SLOs (1 h fast burn + 6 h slow burn).
