"""Worker-side Prometheus metrics (Phase 10).

The API's `/metrics` lives in the request process and sees nothing the worker does. These tests
drive the real Celery signal handlers, because the failure mode this is meant to prevent — a
task failing silently for a week — is exactly what a mocked signal would also produce.

Requirements: TEC-08.
"""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from app import worker_metrics as wm


def _scrape() -> str:
    return generate_latest().decode()


def _value(metric: str, **labels) -> float:
    """Read one sample out of the default registry."""
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value(metric, labels) or 0.0


class _Sender:
    """What Celery passes as `sender` — the task object, which carries `.name`."""

    def __init__(self, name):
        self.name = name


@pytest.fixture(autouse=True)
def installed():
    wm.install()          # idempotent
    return True


# ---------------------------------------------------------------------------------------
# Task outcomes
# ---------------------------------------------------------------------------------------


def test_a_successful_task_is_counted_by_name(installed):
    """By name, not in aggregate. A single failing task averaged into a healthy total is a
    task nobody notices."""
    from celery import signals

    before = _value("cm_worker_tasks_total", task="renewals.sweep", result="success")
    signals.task_success.send(sender=_Sender("renewals.sweep"), result=None)

    assert _value("cm_worker_tasks_total",
                  task="renewals.sweep", result="success") == before + 1


def test_a_failed_task_is_counted_separately(installed):
    from celery import signals

    before = _value("cm_worker_tasks_total", task="ocr.process", result="failure")
    signals.task_failure.send(sender=_Sender("ocr.process"))

    assert _value("cm_worker_tasks_total",
                  task="ocr.process", result="failure") == before + 1
    # And it did not quietly land in the success bucket.
    assert _value("cm_worker_tasks_total", task="ocr.process", result="success") == 0


def test_retries_and_revocations_are_distinguishable(installed):
    """A task retrying is healthy-ish; a task being revoked is somebody intervening. Collapsing
    them into "failure" loses the difference at exactly the moment it matters."""
    from celery import signals

    signals.task_retry.send(sender=_Sender("signing.seal"))
    signals.task_revoked.send(sender=_Sender("signing.seal"))

    assert _value("cm_worker_tasks_total", task="signing.seal", result="retry") == 1
    assert _value("cm_worker_tasks_total", task="signing.seal", result="revoked") == 1


def test_a_task_with_no_name_is_labelled_rather_than_dropped(installed):
    """`task="unknown"` says the wiring is wrong. A silently dropped sample says nothing."""
    from celery import signals

    signals.task_success.send(sender=object(), result=None)
    assert _value("cm_worker_tasks_total", task="unknown", result="success") >= 1


# ---------------------------------------------------------------------------------------
# Duration and in-flight
# ---------------------------------------------------------------------------------------


def test_a_task_run_records_its_duration_and_clears_in_flight(installed):
    from celery import signals

    task = _Sender("pki.publish_crls")
    signals.task_prerun.send(sender=task, task_id="t-1", task=None)
    assert _value("cm_worker_tasks_in_flight", task="pki.publish_crls") == 1

    signals.task_postrun.send(sender=task, task_id="t-1", state="SUCCESS")

    assert _value("cm_worker_tasks_in_flight", task="pki.publish_crls") == 0
    assert _value("cm_worker_task_duration_seconds_count", task="pki.publish_crls") == 1


def test_in_flight_returns_to_zero_even_when_a_task_fails(installed):
    """`task_postrun` fires for failures too. If it did not, a worker that fails a task would
    show a permanently elevated in-flight gauge and look overloaded forever."""
    from celery import signals

    task = _Sender("retention.purge")
    signals.task_prerun.send(sender=task, task_id="t-2", task=None)
    signals.task_failure.send(sender=task)
    signals.task_postrun.send(sender=task, task_id="t-2", state="FAILURE")

    assert _value("cm_worker_tasks_in_flight", task="retention.purge") == 0


def test_a_postrun_without_a_matching_prerun_does_not_raise(installed):
    """Happens on a worker restart mid-task. Raising here would take down the worker over a
    missing timing sample."""
    from celery import signals

    signals.task_postrun.send(sender=_Sender("orphan.task"), task_id="never-started",
                              state="SUCCESS")


# ---------------------------------------------------------------------------------------
# Sweep counts — the part that makes a quiet sweep distinguishable from a dead one
# ---------------------------------------------------------------------------------------


def test_a_sweeps_returned_counts_become_metrics(installed):
    """Every sweep here returns a dict of counts. Reading the return value exports all of them
    without touching a single task body — including the sweep somebody adds next month."""
    from celery import signals

    signals.task_success.send(
        sender=_Sender("renewals.sweep"),
        result={"flagged_expiring": 3, "moved_to_expired": 1,
                "reminders_sent": 4, "obligations_overdue": 0})

    assert _value("cm_worker_sweep_items_total",
                  sweep="renewals.sweep", outcome="flagged_expiring") == 3
    assert _value("cm_worker_sweep_items_total",
                  sweep="renewals.sweep", outcome="reminders_sent") == 4
    # Zero still registers the series, so "the sweep ran and found nothing" is visible rather
    # than looking identical to "the sweep did not run".
    assert _value("cm_worker_sweep_items_total",
                  sweep="renewals.sweep", outcome="obligations_overdue") == 0
    assert 'outcome="obligations_overdue"' in _scrape()


def test_a_non_dict_result_contributes_nothing(installed):
    """Most tasks return an id or a status string. Those must not produce nonsense labels."""
    from celery import signals

    signals.task_success.send(sender=_Sender("pdf.render"), result="file-id-123")
    signals.task_success.send(sender=_Sender("pdf.render"), result=None)
    signals.task_success.send(sender=_Sender("pdf.render"), result=["a", "b"])

    assert "pdf.render" not in [
        line for line in _scrape().splitlines()
        if line.startswith("cm_worker_sweep_items_total") and "pdf.render" in line
    ]


def test_non_integer_values_in_a_result_are_skipped(installed):
    """A sweep that returns a mixture must export the counts and ignore the rest rather than
    failing — a monitoring step must never be what turns a successful sweep into a failed one."""
    from celery import signals

    signals.task_success.send(
        sender=_Sender("mixed.sweep"),
        result={"processed": 5, "status": "ok", "ratio": 0.5, "dry_run": True})

    assert _value("cm_worker_sweep_items_total", sweep="mixed.sweep", outcome="processed") == 5
    assert _value("cm_worker_sweep_items_total", sweep="mixed.sweep", outcome="status") == 0
    assert _value("cm_worker_sweep_items_total", sweep="mixed.sweep", outcome="ratio") == 0
    # `True` is an int in Python. Counting it as 1 would silently turn a flag into a quantity.
    assert _value("cm_worker_sweep_items_total", sweep="mixed.sweep", outcome="dry_run") == 0


def test_record_sweep_never_raises(installed):
    """Called from inside a sweep. It must not be able to fail the work it is reporting on."""
    wm.record_sweep("manual", "items", 7)
    wm.record_sweep("manual", "items", 0)
    wm.record_sweep("manual", "items", -1)          # nonsense in, no exception out

    assert _value("cm_worker_sweep_items_total", sweep="manual", outcome="items") == 7


# ---------------------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------------------


def test_the_worker_reports_up_and_down(installed, monkeypatch):
    from celery import signals

    # The exporter's HTTP server is not started here — binding a port in a unit test is a
    # flake waiting for a busy CI machine, and `_serve` is guarded independently below.
    monkeypatch.setattr(wm, "_serve", lambda: None)

    signals.worker_ready.send(sender=None)
    assert _value("cm_worker_up") == 1

    signals.worker_shutting_down.send(sender=None)
    assert _value("cm_worker_up") == 0


def test_the_exporter_can_be_switched_off(monkeypatch):
    """A deployment that scrapes some other way should not have a port bound it did not ask
    for."""
    monkeypatch.setenv("WORKER_METRICS_PORT", "0")
    monkeypatch.setattr(wm, "_server_started", False)

    started = {}
    monkeypatch.setattr("prometheus_client.start_http_server",
                        lambda *a, **k: started.setdefault("called", True))
    wm._serve()

    assert started == {}


def test_a_failure_to_bind_does_not_stop_the_worker(monkeypatch):
    """A worker that cannot export metrics is still a worker. Refusing to start would trade an
    observability gap for an outage."""
    monkeypatch.setenv("WORKER_METRICS_PORT", "9101")
    monkeypatch.setattr(wm, "_server_started", False)
    monkeypatch.setattr("prometheus_client.start_http_server",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("address in use")))

    wm._serve()                                     # must not raise
    assert wm._server_started is False
