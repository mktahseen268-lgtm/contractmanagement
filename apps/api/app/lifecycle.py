"""The contract lifecycle state machine (a simplified version of docs/06 + docs/01 §4.2)."""

# status -> set of statuses you can move to from there
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_review", "out_for_signature", "voided"},
    "in_review": {"approved", "changes_requested", "rejected"},
    "changes_requested": {"draft", "in_review", "voided"},
    "approved": {"out_for_signature", "active"},
    "out_for_signature": {"signed", "declined", "voided", "approved"},  # "approved" = recall the envelope
    "signed": {"active"},
    "active": {"expiring", "terminated", "renewed"},
    "expiring": {"active", "expired", "renewed", "terminated"},
    "expired": {"renewed"},
    "rejected": {"draft"},
    "declined": {"draft", "voided"},
    "terminated": set(),
    "voided": set(),
    "renewed": set(),
    "superseded": set(),
}

ALL_STATUSES = list(TRANSITIONS.keys())

# The "spine" shown in the LifecycleBar (order matters for the UI).
SPINE = ["draft", "in_review", "approved", "out_for_signature", "signed", "active", "expiring"]

# Friendly labels for the action buttons the API advertises.
TRANSITION_LABELS: dict[str, str] = {
    "in_review": "Submit for approval",
    "approved": "Approve",
    "changes_requested": "Request changes",
    "rejected": "Reject",
    "out_for_signature": "Send for signature",
    "signed": "Mark as signed",
    "active": "Activate",
    "declined": "Mark declined",
    "expiring": "Flag as expiring",
    "expired": "Mark expired",
    "renewed": "Mark renewed",
    "terminated": "Terminate",
    "voided": "Void",
    "draft": "Return to draft",
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def available(current: str) -> list[str]:
    return sorted(TRANSITIONS.get(current, set()))
