# 22 · Infrastructure, Deployment & Operations

Target topologies, HA design, backup / DR, and the data-retention regime.

## 1. Reference topology (production)

```
                      ┌────────────────────┐
                      │  CDN + WAF + DDoS  │   Cloudflare / AWS WAF / Azure FrontDoor
                      └──────────┬─────────┘
                                 │ TLS 1.3
                      ┌──────────▼─────────┐
                      │   Load Balancer     │   NLB/ALB · App Gateway · Ingress-NGINX
                      └──────────┬─────────┘
              ┌──────────────────┼──────────────────┐
              │                  │                  │
        ┌─────▼────┐       ┌─────▼────┐       ┌─────▼────┐
        │ web pod  │ ×N    │ api pod  │ ×N    │ worker   │ ×N   Celery — `default` + `ocr` queues
        │ (Next.js)│       │ (FastAPI)│       │ (Celery) │
        └─────┬────┘       └─────┬────┘       └─────┬────┘
              │                  │ JWT / API key      │
              └──────────────────┼────────────────────┘
                                 │
            ┌────────────────────┼──────────────────────────┐
            │                    │                          │
      ┌─────▼─────┐        ┌─────▼─────┐            ┌───────▼────────┐
      │ PostgreSQL│ HA     │  Redis    │ HA         │ S3-compat OBJ  │ versioned
      │  primary  │◀──────│ Sentinel/  │            │ SSE-KMS, per-  │ + replicated
      │ +standby ×2│  Bus  │ Cluster   │            │ tenant prefix  │
      └───────────┘        └───────────┘            └────────────────┘
```

Stateless pods scale horizontally via the HPA on CPU + custom RPS metric.

## 2. Multi-tier architecture

| Tier | Components | Trust boundary | Scaling |
|---|---|---|---|
| **Edge** | CDN, WAF, DDoS, TLS termination | Internet | Provider-managed |
| **App** | API (FastAPI), Web (Next.js), Worker (Celery), Beat (single) | Cluster | Horizontal — HPA |
| **Data** | Postgres primary + 2 standbys, Redis (Sentinel or Cluster), S3-compatible object storage | Private subnet, network-policied | Read-replicas + sharding (future) |
| **Observability** | Loki/Splunk/Elastic, Prometheus + Grafana, Sentry, OTel collector | Private | Provider-managed |

## 3. High availability

- **API / Web / Worker**: ≥ 2 replicas, pod anti-affinity by zone, HPA min=2 / max=12,
  rolling update strategy `maxSurge=25% maxUnavailable=0`.
- **PostgreSQL**: managed service preferred (RDS Multi-AZ / Azure Flexible Server / CloudSQL HA).
  Self-managed alt: Patroni + etcd with 1 primary + 2 sync standbys; HAProxy in front.
- **Redis**: Sentinel (3 nodes, quorum=2) for self-managed; ElastiCache Multi-AZ or
  Azure Cache for Redis Premium for managed.
- **Celery worker**: 2+ workers per queue, `task_acks_late=True`, `task_reject_on_worker_lost=True`
  (already set), and `worker_max_tasks_per_child=200` (cycles to flush leaks). Beat runs as a
  **leader-elected** singleton (k8s lease).
- **Object storage**: cross-region replication on the bucket; lifecycle to Glacier after 90 days.

RPO ≤ 5 min (Postgres async standby), RTO ≤ 15 min (managed failover) / ≤ 60 min (self-managed).

## 4. Kubernetes manifests

Sample manifests live in [`infra/k8s/`](../infra/k8s/):

```
infra/k8s/
├── namespace.yaml
├── configmap.yaml
├── secret.example.yaml          # template — fill via External Secrets / Vault
├── deployment-api.yaml          # liveness + readiness; resource requests/limits; topology spread
├── deployment-web.yaml
├── deployment-worker.yaml
├── deployment-beat.yaml         # singleton, leaderElection annotation
├── service-api.yaml
├── service-web.yaml
├── ingress.yaml                 # TLS, rate-limit annotation, WAF-friendly
├── hpa-api.yaml                 # cpu>70% OR rps>... → scale
├── hpa-web.yaml
├── hpa-worker.yaml
├── networkpolicy.yaml           # default-deny + explicit allow
├── poddisruptionbudget.yaml     # minAvailable: 1 per deployment
└── servicemonitor.yaml          # Prometheus operator
```

Apply: `kubectl apply -k infra/k8s` (a `kustomization.yaml` wires it).

## 5. Load balancer / Ingress

NGINX ingress example (snippet):

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/limit-rps: "120"
    nginx.ingress.kubernetes.io/limit-burst-multiplier: "2"
    nginx.ingress.kubernetes.io/proxy-body-size: "60m"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "Referrer-Policy: strict-origin-when-cross-origin";
      proxy_set_header X-Forwarded-For $proxy_protocol_addr;
spec:
  tls:
    - hosts: [app.example.com, api.example.com]
      secretName: app-tls
```

Compatible drop-ins: **Kong**, **AWS ALB Ingress Controller**, **Traefik**, **Istio Gateway**.
The API consumes `X-Forwarded-For` correctly via `client_ip()` in `deps.py`.

## 6. TLS profile

Minimum TLS 1.2; prefer 1.3. Cipher allowlist (modern profile):

```
ECDHE-ECDSA-AES128-GCM-SHA256
ECDHE-RSA-AES128-GCM-SHA256
ECDHE-ECDSA-AES256-GCM-SHA384
ECDHE-RSA-AES256-GCM-SHA384
ECDHE-ECDSA-CHACHA20-POLY1305
ECDHE-RSA-CHACHA20-POLY1305
```

OCSP stapling **on**. HSTS preload submission after 6 months of stable rollout.

## 7. Backup & Disaster Recovery

### 7.1 Backups

- **Database**: nightly full + PITR (point-in-time recovery) via WAL archive.
  - Managed: RDS automated backups, 35-day retention, enable enhanced monitoring.
  - Self-managed: `pgbackrest` with full+diff+incremental + WAL push to S3.
- **Object storage**: cross-region replication; lifecycle to Glacier after 90 days; 10-year
  retention; versioning enabled.
- **Secrets** & infra config: stored in IaC (Terraform / Pulumi); state in encrypted backend.
- **Test restore**: a quarterly drill restores last night's backup into a staging environment
  and runs the smoke suite. Pass/fail is recorded in the compliance ledger.

A one-shot helper script is included: [`infra/scripts/backup.sh`](../infra/scripts/backup.sh).

### 7.2 DR scenarios

| Scenario | Detection | Response | Target |
|---|---|---|---|
| Pod crash / node loss | k8s liveness + Prometheus | Auto-restart, HPA scale-out | < 1 min |
| AZ outage | Provider health | Multi-AZ DB failover, ingress routes to surviving AZ | RTO 5 min |
| Region outage | Manual + provider | Restore from cross-region snapshot + WAL replay; DNS cutover | RTO 60 min · RPO 15 min |
| Database corruption | Application errors / consistency check | PITR to last good LSN; replay; reconcile | RTO 2 h · RPO 5 min |
| Ransomware on object storage | S3 ETag / inventory diff | Restore from versioned previous + Glacier copy | Per asset |

Runbooks live in [`infra/runbooks/`](../infra/runbooks/).

## 8. Data archiving, purging, retention

Retention policy (configurable per tenant where regulation requires):

| Data class | Hot (instant search) | Cold (archived) | Total retention |
|---|---|---|---|
| Contracts (active + terminal states) | **forever** (or to tenant deletion) | n/a | per agreement |
| Executed PDFs + certificates | **forever** (S3 hot) | Glacier > 5 y | per agreement |
| **Audit log** | **1 year** in DB | Parquet on S3 (queryable via Athena/Glue) | **10 years** |
| Webhook deliveries | 90 days in DB | n/a | 90 days |
| Background jobs | 90 days in DB | n/a | 90 days |
| Email outbox | 30 days in DB | n/a | 30 days |
| Sessions (refresh) | until `expires_at + 14 days` | n/a | n/a |
| OTP / recovery codes used | until next purge cycle (≤24 h) | n/a | n/a |

Implemented by the `retention.purge` Celery beat task (`apps/api/app/tasks.py`), running
nightly:

1. Move audit-log rows older than **1 year** to S3 (compressed Parquet, partitioned by
   `tenant_id` + month) — **archive** then **delete from hot store**.
2. Delete audit-log rows older than **10 years** (after archive verification).
3. Delete `webhook_deliveries` older than 90 days.
4. Delete `background_jobs` older than 90 days.
5. Delete `email_outbox` rows older than 30 days.
6. Hard-delete used `recovery_codes` / `otp_codes` older than 24 hours.

The job is **idempotent** and logs a `retention.purge_complete` audit event with counts.

## 9. Capacity planning (starter sizing)

| Component | Small (≤ 10 tenants, ≤ 10 k contracts) | Medium (≤ 100 tenants, ≤ 1 M contracts) | Large (1 k tenants, 10 M contracts) |
|---|---|---|---|
| API pods | 2 × (500 m / 512 Mi) | 4–8 × (1 / 1 Gi) | 12+ × (2 / 2 Gi) |
| Worker pods | 2 × (500 m / 512 Mi) | 4 × (1 / 1 Gi) | 8 × (2 / 2 Gi) |
| Postgres | 2 vCPU / 8 Gi | 8 vCPU / 32 Gi + read replica | Aurora-class 16 vCPU + replicas |
| Redis | 1 Gi single | 6 Gi cluster (3 shards) | 32 Gi cluster |
| S3 | < 1 TB | < 50 TB | per usage |
