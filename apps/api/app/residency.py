"""Data-residency enforcement for the on-prem deployment profile.

The RFP requires on-premises hosting with all data — contract content, signatory PII, key
material, audit logs — inside Pakistan. This module is the boot-time control that makes that
claim checkable rather than asserted.

**We deliberately do not geo-locate IPs at runtime.** Every GeoIP service is a foreign-hosted
lookup, which is precisely the dependency the requirement forbids, and a bundled MaxMind
database is stale the day it ships. Instead we enforce the property that actually matters for
an air-gapped/on-prem install:

    every configured egress endpoint must resolve to a private, loopback or link-local
    address, or be named explicitly in DATA_RESIDENCY_ALLOW_HOSTS.

A hostname that resolves to a public address is either a foreign SaaS (a violation) or a
deliberate, documented exception the operator lists in the allowlist — where it shows up in
config review and in the residency statement, which is where an auditor can see it.

Startup calls `enforce()`; it raises on violation when `DATA_RESIDENCY_ENFORCED` is true and
records a `residency_check` audit entry either way.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import settings

log = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Endpoint:
    label: str          # which setting this came from
    host: str
    setting: str        # env var name, for the error message


@dataclass(frozen=True)
class Finding:
    endpoint: Endpoint
    addresses: list[str]
    ok: bool
    reason: str


def _host_of(value: str) -> str:
    """Hostname from a URL, a host:port pair, or a bare hostname."""
    if not value:
        return ""
    v = value.strip()
    if "://" in v:
        return urlsplit(v).hostname or ""
    # host:port — but not an unbracketed IPv6 literal
    if v.count(":") == 1:
        return v.split(":", 1)[0]
    return v


def collect_endpoints() -> list[Endpoint]:
    """Every configured destination this process can send data to.

    Deliberately includes the datastores: a Postgres or Redis URL pointing at a managed cloud
    instance is the single most likely way contract data leaves the country.
    """
    candidates = [
        ("object storage", settings.s3_endpoint_url, "S3_ENDPOINT_URL"),
        ("smtp", settings.smtp_host, "SMTP_HOST"),
        ("otel collector", settings.otel_exporter_otlp_endpoint, "OTEL_EXPORTER_OTLP_ENDPOINT"),
        ("timestamp authority", settings.signing_tsa_url, "SIGNING_TSA_URL"),
        ("oidc issuer", settings.oidc_issuer, "OIDC_ISSUER"),
        ("database", settings.database_url, "DATABASE_URL"),
        ("redis", settings.redis_url, "REDIS_URL"),
        ("celery broker", settings.celery_broker_url, "CELERY_BROKER_URL"),
    ]
    # The OCR provider only reaches out when it is actually the configured provider.
    if settings.ocr_provider == "anthropic":
        candidates.append(("ocr provider", "api.anthropic.com", "OCR_PROVIDER"))
    if settings.ocr_provider == "local":
        candidates.append(("ocr provider", settings.ocr_base_url, "OCR_BASE_URL"))
    # The writing assistant sees draft contract text, so it is checked like any other
    # destination — "it is a local model" is a claim about a URL, and this is what tests it.
    if settings.text_assist_provider == "local":
        candidates.append(("writing assistant", settings.text_assist_base_url,
                           "TEXT_ASSIST_BASE_URL"))

    out: list[Endpoint] = []
    seen: set[tuple[str, str]] = set()
    for label, raw, setting in candidates:
        host = _host_of(raw)
        if not host or host in ("localhost", "::1"):
            continue
        if (label, host) in seen:
            continue
        seen.add((label, host))
        out.append(Endpoint(label=label, host=host, setting=setting))
    return out


def _allowlisted(host: str, addrs: list[str]) -> bool:
    allow = settings.data_residency_allow_host_list
    if not allow:
        return False
    for entry in allow:
        if entry.lower() == host.lower():
            return True
        try:
            net = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        for a in addrs:
            try:
                if ipaddress.ip_address(a) in net:
                    return True
            except ValueError:
                continue
    return False


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos})


def check() -> list[Finding]:
    """Resolve every endpoint and classify it. Never raises — `enforce` decides what to do."""
    findings: list[Finding] = []
    for ep in collect_endpoints():
        addrs = _resolve(ep.host)
        if not addrs:
            # Unresolvable at boot is not a residency violation — the host may simply be down,
            # or DNS may not be up yet in a compose/k8s start order. Report, do not block.
            findings.append(Finding(ep, [], True, "unresolvable at boot (not checked)"))
            continue
        if _allowlisted(ep.host, addrs):
            findings.append(Finding(ep, addrs, True, "explicitly allowlisted"))
            continue
        public = [
            a for a in addrs
            if not (
                ipaddress.ip_address(a).is_private
                or ipaddress.ip_address(a).is_loopback
                or ipaddress.ip_address(a).is_link_local
            )
        ]
        if public:
            findings.append(
                Finding(ep, addrs, False, f"resolves to public address(es): {', '.join(public)}")
            )
        else:
            findings.append(Finding(ep, addrs, True, "private/loopback address"))
    return findings


def enforce() -> list[Finding]:
    """Boot-time gate. Raises RuntimeError on violation when enforcement is on."""
    findings = check()
    violations = [f for f in findings if not f.ok]
    for f in findings:
        level = log.error if not f.ok else log.info
        level(
            "residency: %s (%s=%s) — %s",
            f.endpoint.label, f.endpoint.setting, f.endpoint.host, f.reason,
        )
    if violations and settings.data_residency_enforced:
        detail = "; ".join(
            f"{v.endpoint.label} ({v.endpoint.setting}={v.endpoint.host}) {v.reason}" for v in violations
        )
        raise RuntimeError(
            f"Data residency check failed for region {settings.data_residency_region}: {detail}. "
            "Point these at on-premises infrastructure, or add them to "
            "DATA_RESIDENCY_ALLOW_HOSTS if the egress is reviewed and documented."
        )
    return findings


def record_boot_check(findings: list[Finding], tenant_id: str) -> None:
    """Write the `residency_check` audit entry. This is the evidence the RFP's hosting &
    data-residency statement points at — it proves the check ran on this deployment, on this
    date, with these endpoints."""
    if not tenant_id:
        return
    from . import audit
    from .database import SessionLocal, set_request_tenant

    try:
        set_request_tenant(tenant_id)
        with SessionLocal() as db:
            audit.record(
                db,
                tenant_id=tenant_id,
                action="residency_check",
                object_type="system",
                object_label=f"region={settings.data_residency_region}",
                meta={
                    "region": settings.data_residency_region,
                    "enforced": settings.data_residency_enforced,
                    "endpoints": [
                        {
                            "label": f.endpoint.label,
                            "setting": f.endpoint.setting,
                            "host": f.endpoint.host,
                            "addresses": f.addresses,
                            "ok": f.ok,
                            "reason": f.reason,
                        }
                        for f in findings
                    ],
                },
            )
            db.commit()
    except Exception:  # noqa: BLE001
        # Never block boot on the audit write — the enforcement above already ran.
        log.exception("residency: failed to record boot audit entry")
