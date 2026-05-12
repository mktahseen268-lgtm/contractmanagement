# 18 — Infrastructure & Scalability

**Docker everywhere, Kubernetes-ready, production-grade, CI/CD-driven.** Designed to run on any K8s (managed — EKS/GKE/AKS — or self-managed for sovereign/on-prem deployments, which the GCC/government market often wants). S3-compatible object storage (AWS S3, or MinIO/Wasabi/Ceph for on-prem). The architecture is "boring where boring is safe, decoupled exactly at the seams that get loaded first."

---

## 1. Runtime topology

```
                         ┌─────────────────────────────────────────────┐
   Internet ──▶ CDN ──▶ WAF ──▶ Ingress (NGINX/Traefik, TLS) ──▶ Kubernetes cluster
   (static,                                                    │
    docs,                  ┌──────────────────┬────────────────┼────────────────┬────────────────┐
    signed-URL             ▼                  ▼                ▼                ▼                ▼
    streaming)        web (Next.js)      api (FastAPI)     collab svc       worker pools      beat (×1)
                      Deployment+HPA     Deployment+HPA    (WS/CRDT)        per queue group:  CronJob-like
                                                          Deploy+HPA       ocr | ai |
                                                                           pdf+email+notif |
                                                                           imports+reports+low
                              │                │                │                │
                              ▼                ▼                ▼                ▼
                       ┌─────────────── shared data plane ─────────────────────────┐
                       │  PostgreSQL primary  +  read replica(s)   (managed: RDS/  │
                       │  CloudSQL/Aurora, or Patroni-HA self-managed) + PgBouncer  │
                       │  Redis (broker + cache + rate-limit + presence)  (managed  │
                       │  ElastiCache/MemoryStore, or Redis Sentinel/Cluster)       │
                       │  S3 / S3-compatible (blobs, per-tenant prefixes, KMS)      │
                       │  (optional: OpenSearch / vector DB when search scales out) │
                       └────────────────────────────────────────────────────────────┘
   Observability sidecars/agents everywhere → Prometheus + Grafana + Loki/ELK + Tempo (OTel) + Sentry + Alertmanager
   Secrets ← Vault / AWS Secrets Manager (via External Secrets Operator). Certs ← cert-manager. Backups ← scheduled jobs + cross-region copy.
```

- **`web`** (Next.js): stateless, behind the ingress + CDN; HPA on CPU + request latency; static assets and ISR pages cached at the CDN edge; SSR/server-component requests hit the pods.
- **`api`** (FastAPI/uvicorn-gunicorn): stateless; HPA on CPU + p95 latency + in-flight requests; readiness gates on DB+Redis reachability; graceful shutdown (finish in-flight requests, deregister from the LB).
- **`collab`** (the editor's WS/CRDT service — Yjs-style): separate so collaborative-editing load never touches the API tier; sticky-by-document routing; can be plan-gated; scaled independently; persists doc state to Postgres/Redis periodically.
- **`worker` pools**: one Deployment per queue group so each scales on its own signal — **`ocr`** (CPU/GPU-heavy, autoscaled on queue *age*, can sit on a GPU node pool for local models or just call managed OCR APIs), **`ai`** (autoscaled on queue age; calls LLM providers or local models), **`pdf+email+notifications`** (interactive-ish, kept with headroom so a PDF render is never stuck behind a bulk import), **`imports+reports+low`** (batchy, can be slow, cheap nodes). Autoscaling via **KEDA** (scale-to-zero when idle, scale-up on queue length/age) — far better than CPU-based HPA for queue workers.
- **`beat`** (exactly one replica — a leader-elected singleton or a managed scheduler): nightly expiry/renewal scan, reminder cadences, SLA-timer scans, report schedules, audit retention/archival, usage rollups, embedding refresh, token/session cleanup, dunning, partition pre-creation, health self-checks.
- **Data plane** is the only stateful part: PostgreSQL (primary + replicas, PgBouncer in front), Redis, S3 — all managed services in cloud deployments, all HA-able in self-managed/on-prem.

---

## 2. Environments & CI/CD

- **Environments:** `local` (Docker Compose: api, worker, beat, web, postgres, redis, minio, mailhog — `docker compose up` and you have the whole stack), `dev`/`preview` (ephemeral per-PR namespaces — spin up the chart, run e2e, tear down), `staging` (prod-shaped, prod-like data volume, where load/security tests run), `production` (multi-AZ; optionally multi-region later). Config differs only by env vars + secrets; the same images promote across envs.
- **CI pipeline** (on every PR): lint + typecheck (TS + Python) → unit tests → build images → run migrations against a fresh DB *and* a prod-shape copy (catch breaking migrations) → integration tests (testcontainers Postgres, RLS on) → frontend build + Storybook build → e2e (Playwright, LTR + RTL + mobile viewport, against a compose stack or a preview env) → security scans (dependency CVEs, container image scan, SAST, secret-scan, IaC scan) → publish images tagged by commit SHA → (on merge to main) deploy to `dev` → promote to `staging` (manual gate) → promote to `production` (manual gate, or progressive). Bitbucket Pipelines (the repo's current host) / GitHub Actions / GitLab CI — the steps are the same.
- **Deploys:** rolling (or blue-green) for `web`/`api`/`collab` with health-gated cutover and instant rollback (keep the previous ReplicaSet); workers drain gracefully (`acks_late` means a killed task re-runs — safe, idempotent); DB migrations run as a pre-deploy K8s `Job` (forward-compatible: add-then-backfill-then-switch-then-drop, never a destructive change in the same deploy as the code that needs the old shape); feature flags decouple "deployed" from "released" (ship dark, ramp gradually, kill instantly).
- **Images:** small, multi-stage, non-root, distroless/slim bases, pinned digests, SBOM generated, signed (cosign); a private registry; vulnerability scanning on push + periodically on what's running.
- **IaC:** Terraform for cloud resources (VPC, subnets, security groups, RDS/Aurora, ElastiCache, S3 buckets + lifecycle policies, KMS keys, IAM roles, the K8s cluster, DNS/Route53, WAF, CloudFront/CDN); Helm/Kustomize for the workloads; everything in `infra/`, reviewed, applied via CI; no click-ops.

---

## 3. Storage, files, CDN

- **S3** is the file store of record; every blob has a `file_objects` row (Doc 15); the app never touches S3 keys directly outside the `files` module. **Per-tenant key prefixes** (`tenants/<id>/…`) for isolation + per-tenant lifecycle/quota accounting. **Uploads** go direct browser→S3 via short-lived presigned PUT URLs (the API never proxies file bytes); **downloads** are short-lived presigned GET URLs (the API returns a `302` to one) or streamed through a thin signed-URL endpoint when watermarking/access-logging per-view is needed.
- **Encryption at rest:** envelope encryption — each blob encrypted with a per-tenant data key (or per-object key) that's wrapped by a KMS master key; bucket-level SSE as a baseline; rotation supported.
- **Lifecycle tiering:** hot (current contract versions, recent files) → infrequent-access (older versions) → cold/archive (very old versions, archived audit partitions) — automatic, transparent to the app via the `lifecycle_tier` field; retrieval-from-cold is async (a job) with a "restoring…" state in the UI.
- **CDN** in front of static assets, the marketing site, and (cacheably) public branding logos; never caches authenticated content or signed URLs.
- **Backups:** S3 versioning + cross-region replication for the buckets; the DB's backups (below) cover the relational store; periodic restore drills verify both.

---

## 4. Observability & ops

- **Logs:** structured JSON, correlated by `request_id` / `tenant_id` / `user_id` / `job_id` / `trace_id`; shipped to Loki/ELK; app logs separate from audit-grade access logs; PII-aware (no secrets, minimal personal data).
- **Metrics (Prometheus):** request rate/latency (p50/p95/p99)/error rate per route; queue depth + **queue age** per queue (the key worker-scaling signal); job success rate + duration + retry count per task type; OCR pages/min, AI tokens/requests, PDF renders/min; DB connection-pool usage, slow-query count, replica lag; cache hit rate; webhook delivery success rate; per-tenant usage counters (feeds billing).
- **Traces (OpenTelemetry → Tempo/Jaeger):** spans across CDN→ingress→api→service→DB→queue→worker→external (OCR/AI/email) — so a slow contract-detail load or a stuck OCR job is traceable end to end.
- **Errors:** Sentry for exceptions (with the `request_id` users can quote to support); release-tagged.
- **SLOs & alerting (Alertmanager → PagerDuty/Opsgenie/Slack):** API availability (e.g., 99.9%), API p95 latency budgets on hot paths, queue age thresholds (e.g., `ocr` age > 5 min ⇒ page), job failure-rate thresholds, replica-lag threshold, error-budget burn-rate alerts, certificate-expiry, backup-job-failed, disk/memory pressure. Dashboards (Grafana) per concern: API health, queue health, OCR/AI throughput & cost, DB health, tenant usage, business KPIs.
- **Health:** `/health` (liveness — am I up?), `/ready` (readiness — can I serve? DB+Redis reachable, migrations applied); workers report heartbeats; beat reports last-run-times.
- **Runbooks:** documented for the common incidents (queue backlog, DB failover, a tenant abusing OCR, a bad deploy, a leaked credential, a hash-chain mismatch) — in `docs/runbooks/` (a future addition).

---

## 5. Database scaling & DR (recap of Doc 15 §5, ops view)

- **HA:** managed Aurora/RDS Multi-AZ (or Patroni + multiple nodes self-managed) — automatic failover; PgBouncer (transaction pooling) in front of the primary and the read replicas; the API routes reporting/analytics/dashboard-aggregate reads to the replicas, transactional traffic to the primary.
- **Performance:** `tenant_id`-leading indexes everywhere; monthly **partitioning** of the big append-only tables (audit, activity, notifications, jobs, webhook deliveries, workflow events) with beat pre-creating partitions and detaching/archiving old ones; pre-computed `report_rollups` so dashboards/reports read O(1); `pg_stat_statements` watched; query plans reviewed for hot paths.
- **DR:** continuous WAL archiving + daily base backups + PITR; backups encrypted; cross-region copies; documented RPO (minutes) / RTO (low hours); automated restore drills; the audit log's externally-anchored head hash provides a post-restore integrity check.
- **The big-tenant / residency escape hatch** (transparent to the app via the repo/session abstraction): shared DB → per-tenant **schema** → per-tenant **database** (a `tenant→DSN` map) → per-tenant **cluster/region**. Multi-region target: tenant pinned to a home region (DB + S3 in-region), `tenant_id` is the shard key, **no cross-region foreign keys exist by design** — so going multi-region is a deployment project, not a re-architecture. Day-1 is single-region shared-everything (cheapest).

---

## 6. Scalability levers — what we pull, in order, as load grows

| When this gets hot | Pull this lever | Why it's already possible |
|---|---|---|
| API request volume | Scale `api`/`web` pods (HPA); add CDN/edge caching; tune queries; add read replicas for reports | stateless tier, sessions in Redis/JWT — pure horizontal scale |
| Heavy job spikes (bulk import of 5,000 PDFs) | Scale the relevant worker pool (KEDA on queue age); interactive queues keep headroom; bulk lands on `low` | named, prioritized queues; per-queue worker Deployments; idempotent tasks |
| OCR/AI cost & throughput | Scale `ocr`/`ai` worker pools (and GPU node pools for local models); switch/blend providers per tenant/plan; rely on result caching; gate advanced AI to higher plans; offer fast/cheap vs thorough modes | OCR & AI are already separate, queue-isolated, provider-pluggable, cache-keyed-by-content-hash |
| DB write/read pressure | Add replicas; ensure partitioning; offload reports to replicas + rollups; PgBouncer tuning; then the schema→DB→cluster escape hatch for the noisiest tenants | `tenant_id` is the shard key; no cross-shard FKs; repo abstracts the connection |
| Storage growth | S3 is effectively infinite; lifecycle-tier old versions to cold; per-tenant quotas + billing | every blob is a `file_objects` row with a `lifecycle_tier`; per-tenant prefixes |
| Real-time / collaboration load | Scale the `collab` service independently; plan-gate real-time collab; shard by document | `collab` is already a separate service, not part of the API tier |
| Search corpus size | Move keyword/relevance to OpenSearch/Meilisearch and/or vectors to a dedicated vector DB, behind the existing `SearchIndex` interface — no caller changes | search is abstracted from day one; Postgres FTS+pgvector is just the first implementation |
| Notification/webhook fan-out | Move the event bus from in-process to Redis Streams (or Kafka/NATS); scale the dispatcher/consumers | the publish/subscribe interface is stable; the transactional outbox guarantees no lost events |
| Data residency / sovereignty demands | Promote the tenant to its own region (DB + S3 in-region); deploy a regional cluster | single-region today but zero design choices block it |
| Cost pressure generally | OCR/AI provider choice + caching + plan-gating; cold-storage tiering; read-replica offload; KEDA scale-to-zero on idle queues; per-plan feature gating so the expensive features are the ones that pay | all of the above are independent dials |

**Bottom line:** every one of these is an isolated, planned move — none requires a rewrite. The monolith is modular enough that OCR, AI, notifications, billing, and the collab service can each be lifted into their own service when their scaling or deploy-cadence needs justify it; the seams are already there.
