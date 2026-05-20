"""OpenTelemetry tracing (RFI T-1 / docs/26) — opt-in and dependency-light.

Tracing is *off by default*. It activates only when `OTEL_ENABLED=true` and an OTLP/HTTP
collector endpoint is configured. The OpenTelemetry packages are optional extras
(`requirements-otel.txt`); if they aren't installed, this module logs a warning and the app
runs normally with no tracing. Prometheus `/metrics` is always available regardless.

Spans: FastAPI request spans (via the auto-instrumentor) + SQLAlchemy query spans, exported to
the collector over OTLP/HTTP. The collector fans out to Jaeger/Tempo/Honeycomb/etc.
"""

from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("uvicorn.error")

_initialized = False


def init_tracing(app) -> bool:
    """Wire OpenTelemetry if enabled + available. Returns True if tracing was activated.
    Safe to call once at startup; never raises (observability must not break boot)."""
    global _initialized
    if _initialized:
        return True
    if not settings.otel_enabled:
        return False
    if not settings.otel_exporter_otlp_endpoint:
        log.warning("OTEL_ENABLED is true but OTEL_EXPORTER_OTLP_ENDPOINT is empty — tracing disabled.")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as e:  # noqa: BLE001 — packages not installed
        log.warning(
            "OpenTelemetry requested but packages are missing (%s). "
            "Install requirements-otel.txt to enable tracing. Continuing without it.",
            e.__class__.__name__,
        )
        return False

    try:
        resource = Resource.create({"service.name": settings.otel_service_name, "deployment.environment": settings.env})
        provider = TracerProvider(resource=resource)
        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        # SQLAlchemy spans are best-effort (separate optional package)
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            from .database import engine

            SQLAlchemyInstrumentor().instrument(engine=engine)
        except Exception:  # noqa: BLE001
            pass
        _initialized = True
        log.info("OpenTelemetry tracing enabled → %s (service=%s)", endpoint, settings.otel_service_name)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to initialise OpenTelemetry tracing: %s — continuing without it.", e)
        return False
