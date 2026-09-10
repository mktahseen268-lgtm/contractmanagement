"""Prometheus metrics for the Celery worker (Phase 10).

The API exposes `/metrics` from inside the request process. The worker is a different process
on a different host with no HTTP server, so none of the work that actually matters operationally
— OCR, sealing an executed envelope, the renewal sweep, CRL publication — was visible to
monitoring at all. A task could fail every time for a week and the only evidence would be in a
log nobody was aggregating.

**How this is wired.** Celery publishes signals for the whole task lifecycle. Subscribing to
them is the only approach that covers every task without touching a single task body, which
matters because the ones most likely to be forgotten are the ones added later.

**Why a separate HTTP server.** A worker has no request loop to hang an endpoint off, so this
starts a small one on its own port (`WORKER_METRICS_PORT`, default 9101) when the worker boots.
Prometheus scrapes it exactly as it scrapes the API.

**Multiprocess caveat, stated rather than discovered.** A Celery worker with `--concurrency>1`
using the prefork pool runs tasks in *child* processes, and a counter incremented in a child is
invisible to the parent's registry. `PROMETHEUS_MULTIPROC_DIR` is the supported answer and is
honoured here when set. Without it the numbers are correct for a `--concurrency=1` worker or the
threads pool, and undercount otherwise — `docs/33-observability.md` says which to run.
"""

from __future__ import annotations

import logging
import os
import time

from prometheus_client import Counter, Gauge, Histogram

log = logging.getLogger("worker.metrics")

#: Task outcomes, labelled by task name so a single failing task is visible rather than being
#: averaged into a healthy total.
TASK_TOTAL = Counter(
    "cm_worker_tasks_total",
    "Celery tasks by name and terminal outcome.",
    ["task", "result"],          # success | failure | retry | revoked
)

TASK_DURATION = Histogram(
    "cm_worker_task_duration_seconds",
    "Celery task execution time.",
    ["task"],
    # Buckets chosen for what these tasks actually do. Sealing an envelope involves PDF
    # rendering and an HSM signature; OCR is slower still. The default buckets top out at 10s
    # and would put every seal in +Inf, which tells you nothing.
    buckets=(0.05, 0.25, 1.0, 5.0, 15.0, 60.0, 300.0, 900.0),
)

TASK_IN_FLIGHT = Gauge(
    "cm_worker_tasks_in_flight",
    "Tasks currently executing on this worker.",
    ["task"],
)

#: Time between a task being published and a worker picking it up. This is the number that
#: says whether the queue is keeping up — execution time can look perfectly healthy while
#: everything waits an hour to start.
TASK_QUEUE_LATENCY = Histogram(
    "cm_worker_task_queue_seconds",
    "Delay between a task being published and starting execution.",
    ["task"],
    buckets=(0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0, 1800.0),
)

WORKER_UP = Gauge(
    "cm_worker_up",
    "1 while this worker process is accepting tasks.",
)

#: Beat-driven sweeps report what they touched. A sweep that runs every hour and processes
#: nothing is indistinguishable from a sweep that is not running at all, unless the count is
#: exported.
SWEEP_ITEMS = Counter(
    "cm_worker_sweep_items_total",
    "Items processed by scheduled sweeps.",
    ["sweep", "outcome"],
)

_started_at: dict[str, float] = {}


def record_sweep(sweep: str, outcome: str, count: int = 1) -> None:
    """Called by a beat task to report what it did. Never raises — a monitoring failure must
    not fail the sweep it is monitoring."""
    try:
        if count:
            SWEEP_ITEMS.labels(sweep=sweep, outcome=outcome).inc(count)
    except Exception:  # noqa: BLE001
        log.debug("worker metrics: sweep counter failed", exc_info=True)


def _report_counts(task: str, result) -> None:
    """Export a task's returned count dict as sweep counters.

    Only integers are taken, and only non-negative ones. A task that returns a payload rather
    than counts contributes nothing rather than producing nonsense labels, and a monitoring
    step must never be the thing that turns a successful sweep into a failed one.
    """
    if not isinstance(result, dict):
        return
    try:
        for key, value in result.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            if value <= 0:
                # Emitting zero would still create the series, which is useful — but `inc(0)`
                # on a Counter is a no-op anyway, so touch the label to register it and move on.
                SWEEP_ITEMS.labels(sweep=task, outcome=str(key)[:64])
                continue
            SWEEP_ITEMS.labels(sweep=task, outcome=str(key)[:64]).inc(value)
    except Exception:  # noqa: BLE001
        log.debug("worker metrics: count export failed for %s", task, exc_info=True)


def _task_name(sender, task_id, kwargs) -> str:
    """The task's registered name, falling back to something greppable.

    Unlabelled metrics are worse than none: `cm_worker_tasks_total{task="unknown"}` at least
    says the wiring is wrong, where a silently dropped sample says nothing at all.
    """
    name = getattr(sender, "name", None)
    return str(name or "unknown")


_installed = False


def install() -> None:
    """Subscribe to Celery's task signals. Idempotent — safe to call more than once.

    Signals rather than a task base class: a base class only covers tasks that remember to use
    it, and the task somebody adds next month will not.

    The guard is load-bearing, not defensive tidiness. `connect(weak=False)` registers a *new*
    closure on every call, so a second `install()` makes every signal fire twice and every
    number double. In production this is called once at import and the fault would never show;
    it surfaced under test, where calling it per-test inflated every counter tenfold. A metric
    that is quietly 2x is worse than no metric, because somebody will make a capacity decision
    with it.
    """
    global _installed
    if _installed:
        return
    _installed = True

    from celery import signals

    @signals.task_prerun.connect(weak=False)
    def _prerun(sender=None, task_id=None, task=None, **_kw):  # noqa: ANN001
        name = _task_name(sender, task_id, None)
        _started_at[task_id] = time.monotonic()
        try:
            TASK_IN_FLIGHT.labels(task=name).inc()
            # `eta`/`time_start` are not reliably present; the publish time rides on the
            # request headers when the producer set it. Missing is normal, not an error.
            request = getattr(task, "request", None)
            published = getattr(request, "published_at", None) if request else None
            if published:
                TASK_QUEUE_LATENCY.labels(task=name).observe(max(0.0, time.time() - published))
        except Exception:  # noqa: BLE001
            log.debug("worker metrics: prerun failed", exc_info=True)

    @signals.task_postrun.connect(weak=False)
    def _postrun(sender=None, task_id=None, state=None, **_kw):  # noqa: ANN001
        name = _task_name(sender, task_id, None)
        try:
            TASK_IN_FLIGHT.labels(task=name).dec()
            started = _started_at.pop(task_id, None)
            if started is not None:
                TASK_DURATION.labels(task=name).observe(time.monotonic() - started)
        except Exception:  # noqa: BLE001
            log.debug("worker metrics: postrun failed", exc_info=True)

    @signals.task_success.connect(weak=False)
    def _success(sender=None, result=None, **_kw):  # noqa: ANN001
        name = _task_name(sender, None, None)
        TASK_TOTAL.labels(task=name, result="success").inc()
        # Every sweep in this codebase returns a dict of counts — `{"flagged_expiring": 3,
        # "reminders_sent": 3, ...}`. Reading it here exports all of them without touching a
        # single task body, and covers the sweep somebody adds next month too. A per-task call
        # would only cover the tasks that remembered to make it.
        _report_counts(name, result)

    @signals.task_failure.connect(weak=False)
    def _failure(sender=None, **_kw):  # noqa: ANN001
        TASK_TOTAL.labels(task=_task_name(sender, None, None), result="failure").inc()

    @signals.task_retry.connect(weak=False)
    def _retry(sender=None, **_kw):  # noqa: ANN001
        TASK_TOTAL.labels(task=_task_name(sender, None, None), result="retry").inc()

    @signals.task_revoked.connect(weak=False)
    def _revoked(sender=None, **_kw):  # noqa: ANN001
        TASK_TOTAL.labels(task=_task_name(sender, None, None), result="revoked").inc()

    @signals.worker_ready.connect(weak=False)
    def _ready(**_kw):
        WORKER_UP.set(1)
        _serve()

    @signals.worker_shutting_down.connect(weak=False)
    def _shutdown(**_kw):
        WORKER_UP.set(0)


_server_started = False


def _serve() -> None:
    """Start the scrape endpoint. Best effort — a worker that cannot export metrics is still a
    worker, and refusing to start it would trade an observability gap for an outage."""
    global _server_started
    if _server_started:
        return

    port = int(os.environ.get("WORKER_METRICS_PORT", "9101"))
    if port <= 0:                       # explicit opt-out
        log.info("worker metrics: disabled (WORKER_METRICS_PORT<=0)")
        return

    try:
        from prometheus_client import start_http_server

        multiproc = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
        if multiproc:
            # The library requires the directory to exist and does not create it. Leaving that
            # to the deployment means the exporter silently reports nothing the first time
            # somebody forgets a volumeMount, so the code owns its own precondition.
            os.makedirs(multiproc, exist_ok=True)
            # Prefork children write to files in this directory; the parent aggregates them.
            # Without it a `--concurrency>1` prefork worker undercounts, because the child that
            # ran the task exits with its counters.
            from prometheus_client import CollectorRegistry, multiprocess

            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            start_http_server(port, registry=registry)
        else:
            start_http_server(port)

        _server_started = True
        log.info("worker metrics: serving on :%d%s", port,
                 " (multiprocess)" if multiproc else "")
    except Exception as e:  # noqa: BLE001
        log.warning("worker metrics: could not start exporter on :%s — %s", port, e)
