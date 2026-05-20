"""Prometheus metrics (RFI T-1 / docs/26). Real, scrapeable counters/histograms exposed at
`/metrics`. No external service needed to *produce* metrics — a Prometheus server scrapes the
endpoint (the K8s deployment already annotates `prometheus.io/scrape`).

HTTP-level metrics are recorded by `middleware/metrics.py`; domain counters are incremented at
the relevant call sites (auth, OCR, signing). All metric names are prefixed `cm_`.

Multi-process note: under multiple uvicorn workers, point `PROMETHEUS_MULTIPROC_DIR` at a shared
dir and use the multiprocess collector. For the single-worker container (the default) and the
per-pod scrape model in K8s, the default in-process registry is correct.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ---- HTTP ----
HTTP_REQUESTS = Counter(
    "cm_http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "cm_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_IN_FLIGHT = Gauge(
    "cm_http_requests_in_flight",
    "HTTP requests currently being served.",
)

# ---- domain ----
AUTH_LOGINS = Counter(
    "cm_auth_logins_total",
    "Login outcomes.",
    ["result"],  # success | failed | locked | mfa_challenge | mfa_failed
)
OCR_JOBS = Counter(
    "cm_ocr_jobs_total",
    "OCR jobs by terminal status.",
    ["status"],  # created | completed | failed
)
SIGNATURE_EVENTS = Counter(
    "cm_signature_events_total",
    "E-signature lifecycle events.",
    ["event"],  # sent | signed | declined | completed | voided | reminder
)
WEBHOOK_DELIVERIES = Counter(
    "cm_webhook_deliveries_total",
    "Outbound webhook deliveries.",
    ["result"],  # ok | failed
)


def render() -> tuple[bytes, str]:
    """Return (payload, content_type) for the /metrics response."""
    return generate_latest(), CONTENT_TYPE_LATEST


# Convenience helpers so call sites don't import label semantics everywhere.
def record_login(result: str) -> None:
    try:
        AUTH_LOGINS.labels(result=result).inc()
    except Exception:  # noqa: BLE001 — metrics must never break business logic
        pass


def record_ocr(status: str) -> None:
    try:
        OCR_JOBS.labels(status=status).inc()
    except Exception:  # noqa: BLE001
        pass


def record_signature(event: str) -> None:
    try:
        SIGNATURE_EVENTS.labels(event=event).inc()
    except Exception:  # noqa: BLE001
        pass
