"""SIEM feed — security events in CEF and CLF, shipped over syslog.

The InfoSec table asks for near-real-time delivery of authentication, access-control,
application-usage, system-activity, security-incident, network and audit-trail events, with
severity levels. This is that feed.

**Why the audit log is the source.** Every security-relevant action already writes an audit
row with an actor, an object, an IP and a tamper-evident chain position. Emitting from a
second, parallel path would mean two records of the same event that can disagree — and the one
the SIEM shows is the one an incident responder trusts. So the SIEM feed is a *projection* of
the audit log, not a competing log.

**Delivery is best-effort and never blocks the request.** A SIEM that is down must not stop
people signing contracts. Failures are counted and logged locally; the audit row is already
durable, so nothing is lost — it can be replayed. The alternative, making the request fail
because a downstream collector is unreachable, turns a monitoring outage into an outage.

`SIEM_ENABLED=false` by default. On-prem collectors only: the endpoint goes through the same
residency allowlist as every other egress.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import socket
import ssl

from .config import settings

log = logging.getLogger("uvicorn.error")

#: Syslog severity, lowest number is most urgent (RFC 5424).
EMERGENCY, ALERT, CRITICAL, ERROR, WARNING, NOTICE, INFORMATIONAL, DEBUG = range(8)

SEVERITY_NAMES = {
    EMERGENCY: "Emergency", ALERT: "Alert", CRITICAL: "Critical", ERROR: "Error",
    WARNING: "Warning", NOTICE: "Notice", INFORMATIONAL: "Informational", DEBUG: "Debug",
}

#: Log categories the InfoSec table enumerates, and the audit actions that belong to each.
#: Prefix match, longest first — `auth.login.failed` is a security incident even though
#: `auth.` is authentication.
CATEGORIES: tuple[tuple[str, str, int], ...] = (
    # (audit action prefix, category, severity)
    ("auth.session.reuse_detected", "security_incident", ALERT),
    ("auth.login.failed", "security_incident", WARNING),
    ("auth.lockout", "security_incident", ALERT),
    ("auth.saml_rejected", "security_incident", WARNING),
    ("auth.mfa.failed", "security_incident", WARNING),
    ("auth.", "authentication", INFORMATIONAL),
    ("user.role", "access_control", NOTICE),
    ("user.", "access_control", INFORMATIONAL),
    ("api_key.", "access_control", NOTICE),
    ("role.", "access_control", NOTICE),
    ("permission.", "access_control", NOTICE),
    ("webhook.", "network", NOTICE),
    ("export.", "audit_trail", NOTICE),
    ("report.", "audit_trail", INFORMATIONAL),
    ("audit.", "audit_trail", NOTICE),
    ("pki.", "system_activity", NOTICE),
    ("certificate.", "system_activity", NOTICE),
    ("signature.", "application_usage", INFORMATIONAL),
    ("envelope.", "application_usage", INFORMATIONAL),
    ("contract.terminated", "application_usage", NOTICE),
    ("contract.", "application_usage", INFORMATIONAL),
    ("clause.", "application_usage", INFORMATIONAL),
    ("template.", "application_usage", INFORMATIONAL),
    ("playbook.", "application_usage", INFORMATIONAL),
    ("party.", "application_usage", INFORMATIONAL),
    ("obligation.", "application_usage", INFORMATIONAL),
    ("workflow.", "application_usage", INFORMATIONAL),
)

#: Actions that always mean somebody should look, whatever their category says.
ESCALATED = {
    "audit.chain_broken": CRITICAL,
    "auth.lockout": ALERT,
    # A replayed refresh token means a credential is loose. Nothing about it is routine.
    "auth.session.reuse_detected": ALERT,
    "party.sanctions_hit": ALERT,
    "contract.legal_hold_placed": NOTICE,
}

_VENDOR = "Thiqa"
_PRODUCT = "ContractManagement"
_VERSION = "1.0"


def is_enabled() -> bool:
    return bool(settings.siem_enabled and settings.siem_host)


def classify(action: str) -> tuple[str, int]:
    """(category, severity) for an audit action. Unknown actions are application usage —
    reported rather than dropped, because an event nobody classified is still an event."""
    if action in ESCALATED:
        category = next((c for p, c, _ in CATEGORIES if action.startswith(p)),
                        "application_usage")
        return category, ESCALATED[action]
    for prefix, category, severity in CATEGORIES:
        if action.startswith(prefix):
            return category, severity
    return "application_usage", INFORMATIONAL


def _cef_escape(value: str, *, extension: bool = False) -> str:
    """CEF escaping. The header and the extension escape different characters, and getting it
    wrong produces events a collector silently drops."""
    text = str(value or "")
    text = text.replace("\\", "\\\\")
    if extension:
        return text.replace("=", "\\=").replace("\n", "\\n").replace("\r", "\\n")
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def to_cef(entry, *, category: str = "", severity: int | None = None) -> str:
    """ArcSight Common Event Format.

    CEF severity runs 0..10 with 10 most severe, the opposite direction from syslog. Mapping
    them the wrong way round produces a dashboard where every critical event looks routine,
    which is a failure nobody notices until an incident.
    """
    resolved_category, resolved_severity = classify(entry.action)
    category = category or resolved_category
    severity = resolved_severity if severity is None else severity
    cef_severity = max(0, min(10, 10 - severity))

    extensions = {
        "rt": int(entry.at.replace(tzinfo=dt.timezone.utc).timestamp() * 1000),
        "src": entry.ip or "",
        "suser": entry.actor_name or "system",
        "suid": entry.actor_id or "",
        "cs1Label": "tenant", "cs1": entry.tenant_id,
        "cs2Label": "objectType", "cs2": entry.object_type or "",
        "cs3Label": "objectId", "cs3": entry.object_id or "",
        "cs4Label": "category", "cs4": category,
        "cn1Label": "auditSeq", "cn1": entry.seq or 0,
        "msg": (entry.object_label or "")[:512],
    }
    body = " ".join(f"{k}={_cef_escape(v, extension=True)}"
                    for k, v in extensions.items() if v not in ("", None))
    header = "|".join([
        "CEF:0", _VENDOR, _PRODUCT, _VERSION,
        _cef_escape(entry.action), _cef_escape(entry.action.replace(".", " ").title()),
        str(cef_severity),
    ])
    return f"{header}|{body}"


def to_clf(entry) -> str:
    """NCSA Common Log Format, for collectors that only speak web-server logs.

    A deliberate approximation: CLF has no field for "who did what to which object", so the
    action is encoded in the request line. Anything richer belongs in CEF, and the operator
    picks which they want.
    """
    stamp = entry.at.strftime("%d/%b/%Y:%H:%M:%S +0000")
    user = re.sub(r"\s+", "_", entry.actor_name or "-")
    target = f"/{entry.object_type or 'event'}/{entry.object_id or '-'}"
    return (f'{entry.ip or "-"} - {user} [{stamp}] '
            f'"{entry.action} {target} CM/1.0" 200 - "-" "-"')


def format_event(entry, fmt: str = "") -> str:
    fmt = (fmt or settings.siem_format or "cef").lower()
    if fmt == "clf":
        return to_clf(entry)
    return to_cef(entry)


def syslog_frame(message: str, severity: int, *, facility: int = 13,
                 hostname: str = "") -> bytes:
    """RFC 5424 with an octet-counted frame.

    Octet counting rather than newline delimiting because the message body can itself contain
    newlines, and a collector splitting on them would tear one event into several — which is
    how an incident becomes unreadable at the worst moment.
    """
    priority = facility * 8 + severity
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    host = hostname or settings.siem_hostname or socket.gethostname()
    header = f"<{priority}>1 {stamp} {host} {_PRODUCT} - - - "
    payload = (header + message).encode("utf-8")
    return f"{len(payload)} ".encode("ascii") + payload


class SiemSender:
    """A syslog connection that reconnects, and never lets a collector outage reach a user."""

    def __init__(self) -> None:
        self._socket: socket.socket | None = None
        self.failures = 0

    def _connect(self) -> socket.socket:
        raw = socket.create_connection(
            (settings.siem_host, settings.siem_port), timeout=settings.siem_timeout)
        if settings.siem_tls:
            context = ssl.create_default_context()
            if settings.siem_ca_path:
                context.load_verify_locations(settings.siem_ca_path)
            if not settings.siem_verify:
                # Explicitly opt-out only. An operator who turns this off has said so in
                # configuration; it is never the default, because an unverified TLS channel
                # to a log collector is a channel an attacker can stand in the middle of.
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            return context.wrap_socket(raw, server_hostname=settings.siem_host)
        return raw

    def send(self, frame: bytes) -> bool:
        """True if it went out. Never raises — the caller is in a request path."""
        for attempt in (1, 2):
            try:
                if self._socket is None:
                    self._socket = self._connect()
                self._socket.sendall(frame)
                self.failures = 0
                return True
            except Exception as e:  # noqa: BLE001 — any transport failure is the same here
                self.close()
                if attempt == 2:
                    self.failures += 1
                    # Logged once per failure, not per event: a collector that has been down
                    # for an hour would otherwise fill the local disk with its own outage.
                    if self.failures in (1, 10, 100) or self.failures % 1000 == 0:
                        log.warning("SIEM delivery failed (%d consecutive): %s",
                                    self.failures, e)
        return False

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:  # noqa: BLE001
                pass
            self._socket = None


_sender: SiemSender | None = None


def get_sender() -> SiemSender:
    global _sender
    if _sender is None:
        _sender = SiemSender()
    return _sender


def reset_sender() -> None:
    """Drop the connection — for tests and for a configuration reload."""
    global _sender
    if _sender is not None:
        _sender.close()
    _sender = None


def emit(entry) -> bool:
    """Ship one audit entry to the SIEM. Best effort by design."""
    if not is_enabled():
        return False
    category, severity = classify(entry.action)
    message = format_event(entry)
    return get_sender().send(syslog_frame(message, severity))


def emit_many(entries) -> dict:
    """Ship a batch, reporting what got through.

    Used by the replay path: because the audit log is the source of truth, a SIEM outage is
    recoverable by re-emitting the rows written while it was down.
    """
    sent = failed = 0
    for entry in entries:
        if emit(entry):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}
