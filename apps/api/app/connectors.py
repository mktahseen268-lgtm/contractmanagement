"""Outbound connectors: Microsoft Teams, SharePoint, and calendar invites.

Three integrations that all share the same shape — an optional, configured destination that
must never be able to break the thing it is notifying about. A Teams channel being unreachable
cannot stop an approval; a SharePoint library being full cannot stop an execution.

**Calendar invites go out as `.ics` through the existing mail pipeline.** That is the whole
implementation, and it is deliberate. An EWS or Graph integration would add an authenticated
connection to Exchange, a token to rotate, and a per-version compatibility surface — to deliver
something every mail client already understands as an attachment. The `.ics` lands in Outlook,
Apple Mail, Thunderbird and anything else, and works against on-prem Exchange with no
configuration at all because it is just mail.

**SharePoint targets on-prem Server as well as Online**, because no MMBL data may leave the
deployment. The seam is a REST upload to a document library; which host that is, is
configuration, and it goes through the same residency allowlist as every other egress.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.error
import urllib.request
import uuid

from .config import settings

log = logging.getLogger("uvicorn.error")

_TIMEOUT = 10

#: Workflow events worth interrupting a channel for. Everything else is noise — a Teams
#: channel that pings on every draft save gets muted within a week, taking the alerts that
#: mattered with it.
NOTIFIABLE = (
    "contract.submitted", "contract.approved", "contract.rejected",
    "contract.changes_requested", "contract.signed", "contract.terminated",
    "contract.classified_non_standard", "workflow.escalated",
    "party.sanctions_hit", "audit.chain_broken",
)

#: Colour down the left edge of the card, by how much attention it wants.
_CARD_COLOURS = {
    "good": "28A745", "attention": "D13438", "warning": "F1C40F", "default": "5B5FC7",
}


class ConnectorError(RuntimeError):
    """Delivery failed. Callers log and continue — never fatal to the work being done."""


def _post_json(url: str, payload: dict, *, headers: dict | None = None) -> bool:
    """POST JSON, returning success rather than raising. Never lets a connector outage out."""
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
            return 200 <= response.status < 300
    except urllib.error.HTTPError as e:
        log.warning("connector rejected the payload (%s): %s", e.code, url)
    except Exception as e:  # noqa: BLE001
        log.warning("connector unreachable (%s): %s", type(e).__name__, url)
    return False


# ---------------------------------------------------------------------------------------
# Microsoft Teams
# ---------------------------------------------------------------------------------------


def teams_enabled() -> bool:
    return bool(settings.teams_enabled and settings.teams_webhook_url)


def adaptive_card(*, title: str, subtitle: str = "", facts: dict | None = None,
                  body: str = "", url: str = "", tone: str = "default") -> dict:
    """An Adaptive Card, wrapped for the Teams incoming-webhook connector.

    Facts rather than prose: someone glancing at a channel needs "who, what, how much, by
    when" as scannable pairs. A paragraph gets skimmed and the number in it gets missed.
    """
    elements: list[dict] = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium",
         "wrap": True},
    ]
    if subtitle:
        elements.append({"type": "TextBlock", "text": subtitle, "isSubtle": True,
                         "spacing": "None", "wrap": True})
    if facts:
        elements.append({
            "type": "FactSet",
            "facts": [{"title": str(k), "value": str(v)} for k, v in facts.items() if v],
        })
    if body:
        elements.append({"type": "TextBlock", "text": body, "wrap": True})

    card: dict = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": elements,
    }
    if url:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "Open in Contract Management",
                            "url": url}]

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": card,
        }],
        # The connector reads this for the left-edge colour; the card itself has no such field.
        "themeColor": _CARD_COLOURS.get(tone, _CARD_COLOURS["default"]),
        "summary": title,
    }


def notify_teams(*, title: str, subtitle: str = "", facts: dict | None = None,
                 body: str = "", url: str = "", tone: str = "default") -> bool:
    if not teams_enabled():
        return False
    return _post_json(settings.teams_webhook_url,
                      adaptive_card(title=title, subtitle=subtitle, facts=facts,
                                    body=body, url=url, tone=tone))


def notify_contract_event(contract, event: str, *, actor_name: str = "",
                          detail: str = "") -> bool:
    """Push one workflow event to the channel, if it is one worth interrupting for."""
    if event not in NOTIFIABLE or not teams_enabled():
        return False

    tone = "default"
    if event in ("contract.rejected", "contract.terminated", "party.sanctions_hit",
                 "audit.chain_broken"):
        tone = "attention"
    elif event in ("contract.approved", "contract.signed"):
        tone = "good"
    elif event in ("contract.changes_requested", "contract.classified_non_standard",
                   "workflow.escalated"):
        tone = "warning"

    return notify_teams(
        title=f"{event.split('.', 1)[-1].replace('_', ' ').title()}: {contract.title}",
        subtitle=contract.reference_no or "",
        facts={
            "Counterparty": contract.counterparty,
            "Value": f"{contract.currency} {contract.value:,.0f}" if contract.value else "",
            "Status": (contract.status or "").replace("_", " ").title(),
            "By": actor_name,
        },
        body=detail,
        url=f"{settings.frontend_url.rstrip('/')}/contracts/{contract.id}",
        tone=tone,
    )


# ---------------------------------------------------------------------------------------
# SharePoint
# ---------------------------------------------------------------------------------------


def sharepoint_enabled() -> bool:
    return bool(settings.sharepoint_enabled and settings.sharepoint_site_url
                and settings.sharepoint_library)


def sharepoint_target(contract, filename: str) -> str:
    """Where an executed agreement lands.

    Filed by year and agreement type rather than in one flat library: a document library with
    forty thousand files in a single folder is one SharePoint refuses to page through.
    """
    year = (contract.effective_date or dt.date.today()).year
    kind = (contract.type or "other").replace("_", "-")
    return f"{settings.sharepoint_library.strip('/')}/{year}/{kind}/{filename}"


def push_to_sharepoint(contract, *, filename: str, payload: bytes,
                       content_type: str = "application/pdf") -> bool:
    """Upload an executed agreement to the document library.

    A copy, not a move: the system of record stays here. SharePoint is where the rest of the
    bank looks for a signed PDF, and a sync that removed the local copy would put the record
    of execution somewhere this application cannot audit.
    """
    if not sharepoint_enabled():
        return False

    target = sharepoint_target(contract, filename)
    url = (f"{settings.sharepoint_site_url.rstrip('/')}"
           f"/_api/web/GetFolderByServerRelativeUrl('{settings.sharepoint_library.strip('/')}')"
           f"/Files/add(url='{target.rsplit('/', 1)[-1]}',overwrite=true)")

    headers = {"Content-Type": content_type, "Accept": "application/json;odata=verbose"}
    if settings.sharepoint_token:
        headers["Authorization"] = f"Bearer {settings.sharepoint_token}"

    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT * 3) as response:  # noqa: S310
            return 200 <= response.status < 300
    except Exception as e:  # noqa: BLE001
        log.warning("SharePoint upload failed for %s: %s", contract.reference_no, e)
        return False


# ---------------------------------------------------------------------------------------
# Calendar invites
# ---------------------------------------------------------------------------------------


def _ics_escape(text: str) -> str:
    """RFC 5545 escaping. An unescaped comma silently truncates a field in most clients."""
    return (str(text or "")
            .replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 caps a line at 75 octets; longer ones are continued with a leading space.

    Clients that reject an over-long line do it silently, so a long agreement title would
    produce an invite that simply never appears in the calendar.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 73:
        return line
    chunks, current = [], b""
    for char in line:
        piece = char.encode("utf-8")
        if len(current) + len(piece) > 73:
            chunks.append(current.decode("utf-8"))
            current = b" "
        current += piece
    chunks.append(current.decode("utf-8"))
    return "\r\n".join(chunks)


def calendar_invite(*, summary: str, starts: dt.date | dt.datetime, description: str = "",
                    organiser_email: str = "", attendees: list[str] | None = None,
                    duration_minutes: int = 30, uid: str = "",
                    reminder_minutes: int = 60 * 24, all_day: bool = False,
                    sequence: int = 0, cancelled: bool = False) -> str:
    """An `.ics` invite, deliverable as a mail attachment.

    Carries a stable `UID` and a `SEQUENCE`, so re-sending updates the existing entry instead
    of adding a second one — which is what makes a moved renewal date usable rather than a
    calendar that slowly fills with obsolete duplicates.
    """
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    event_uid = uid or f"{uuid.uuid4().hex}@contract-management"

    if all_day or isinstance(starts, dt.date) and not isinstance(starts, dt.datetime):
        day = starts if isinstance(starts, dt.date) else starts.date()
        start_line = f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}"
        end_line = f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}"
    else:
        begin = starts if isinstance(starts, dt.datetime) else dt.datetime.combine(
            starts, dt.time(9, 0))
        finish = begin + dt.timedelta(minutes=duration_minutes)
        start_line = f"DTSTART:{begin.strftime('%Y%m%dT%H%M%S')}"
        end_line = f"DTEND:{finish.strftime('%Y%m%dT%H%M%S')}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Thiqa//Contract Management//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{'CANCEL' if cancelled else 'REQUEST'}",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTAMP:{stamp}",
        f"SEQUENCE:{sequence}",
        start_line,
        end_line,
        f"SUMMARY:{_ics_escape(summary)}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    if organiser_email:
        lines.append(f"ORGANIZER:mailto:{organiser_email}")
    for attendee in (attendees or []):
        lines.append(
            f"ATTENDEE;RSVP=TRUE;CN={_ics_escape(attendee)}:mailto:{attendee}")
    if reminder_minutes and not cancelled:
        lines += [
            "BEGIN:VALARM",
            f"TRIGGER:-PT{int(reminder_minutes)}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_escape(summary)}",
            "END:VALARM",
        ]
    lines += ["END:VEVENT", "END:VCALENDAR"]

    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def renewal_invite(contract, *, attendees: list[str] | None = None) -> str | None:
    """A calendar entry for the day an agreement expires.

    The UID is derived from the contract id, so re-issuing after the end date moves updates
    the same entry rather than leaving the old date in everybody's calendar alongside the new.
    """
    if not contract.end_date:
        return None
    return calendar_invite(
        summary=f"Renewal due: {contract.title}",
        starts=contract.end_date,
        all_day=True,
        description=(f"{contract.reference_no} with {contract.counterparty or 'the counterparty'} "
                     f"expires today.\n"
                     f"{settings.frontend_url.rstrip('/')}/contracts/{contract.id}"),
        attendees=attendees or [],
        uid=f"renewal-{contract.id}@contract-management",
        reminder_minutes=60 * 24 * 7,
    )


def review_invite(contract, *, due_at: dt.datetime, attendees: list[str] | None = None,
                  step_name: str = "Review") -> str:
    """A deadline entry for a review step."""
    return calendar_invite(
        summary=f"{step_name} due: {contract.title}",
        starts=due_at,
        description=(f"{contract.reference_no} is waiting on you.\n"
                     f"{settings.frontend_url.rstrip('/')}/contracts/{contract.id}"),
        attendees=attendees or [],
        uid=f"review-{contract.id}-{step_name.lower().replace(' ', '-')}@contract-management",
        duration_minutes=30,
        reminder_minutes=60 * 4,
    )


def status() -> dict:
    """What is wired up, for the connectors screen. Reports destinations, never credentials."""
    return {
        "teams": {
            "enabled": teams_enabled(),
            "configured": bool(settings.teams_webhook_url),
            "events": list(NOTIFIABLE),
        },
        "sharepoint": {
            "enabled": sharepoint_enabled(),
            "site_url": settings.sharepoint_site_url,
            "library": settings.sharepoint_library,
            "authenticated": bool(settings.sharepoint_token),
        },
        "calendar": {
            # Always available: an .ics is an attachment on a mail we already send, so there
            # is nothing to configure and nothing to break.
            "enabled": True,
            "transport": "ics attachment over the existing mail pipeline",
        },
    }
