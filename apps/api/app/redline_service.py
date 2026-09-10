"""Redline — compare two versions of an agreement, accept or reject each change.

The negotiation loop this exists for: a counterparty returns a marked-up document, somebody has
to see precisely what moved, and then decide change by change what survives. Doing that by
reading two documents side by side is how a changed liability cap gets waved through.

**No new tables.** A redline is derived, not stored: `ContractVersion` rows are immutable, so
comparing the same pair always produces the same list of changes in the same order. That makes
the position of a change a stable identifier, and "accept changes 0, 2 and 5" a request the
server can honour reproducibly without persisting a session somebody would then have to
garbage-collect. If versions were mutable this would be wrong — they are not.

Tokenisation keeps whitespace as tokens, so accepting *every* change reconstructs the compared
text byte for byte and accepting *none* reconstructs the base. Those two properties are what
make accept/reject trustworthy, and both are tested.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

#: Words and whitespace runs as separate tokens. Whitespace is kept rather than normalised so
#: reconstruction is exact — a diff that quietly reflows the document is not a diff.
_TOKEN_RE = re.compile(r"\S+|\s+")

#: Words of unchanged text shown either side of a change, so a reviewer can place it.
CONTEXT_WORDS = 12


class RedlineError(ValueError):
    """Bad comparison request. Routers map to 400."""


def tokenise(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


@dataclass
class Change:
    """One accept-or-reject decision.

    `index` is the position in the change list and is what the caller sends back. It is stable
    for a given (base, compare) pair because both are immutable and the diff is deterministic.
    """

    index: int
    #: insert | delete | replace
    kind: str
    before: str = ""
    after: str = ""
    before_context: str = ""
    after_context: str = ""
    #: Character range in the compared text, so a comment can be anchored to the proposal.
    anchor_start: int = 0
    anchor_end: int = 0

    def to_dict(self) -> dict:
        return {
            "index": self.index, "kind": self.kind,
            "before": self.before, "after": self.after,
            "before_context": self.before_context, "after_context": self.after_context,
            "anchor_start": self.anchor_start, "anchor_end": self.anchor_end,
        }


@dataclass
class Redline:
    changes: list[Change] = field(default_factory=list)
    #: Words added, removed, and unchanged — the headline "how much moved" numbers.
    added: int = 0
    removed: int = 0
    unchanged: int = 0

    @property
    def identical(self) -> bool:
        return not self.changes

    def to_dict(self) -> dict:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "added": self.added, "removed": self.removed, "unchanged": self.unchanged,
            "identical": self.identical,
            "change_count": len(self.changes),
        }


def _words(tokens: list[str]) -> int:
    return sum(1 for t in tokens if t.strip())


def _context(tokens: list[str], start: int, end: int) -> tuple[str, str]:
    """(before, after) context around a token slice, trimmed to whole words."""
    lead = [t for t in tokens[max(0, start - CONTEXT_WORDS * 2):start]]
    trail = [t for t in tokens[end:end + CONTEXT_WORDS * 2]]
    return "".join(lead).lstrip(), "".join(trail).rstrip()


def compare(base: str, proposed: str) -> Redline:
    """Word-level diff between two texts.

    Adjacent non-equal opcodes are **not** merged: difflib already emits at most one opcode per
    contiguous region, and merging across an equal run would force a reviewer to accept two
    unrelated edits together.
    """
    before_tokens = tokenise(base)
    after_tokens = tokenise(proposed)
    matcher = difflib.SequenceMatcher(None, before_tokens, after_tokens, autojunk=False)

    changes: list[Change] = []
    added = removed = unchanged = 0
    # Character offsets into `proposed`, tracked as we walk so anchors are exact.
    after_offset = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        after_text = "".join(after_tokens[j1:j2])
        if tag == "equal":
            unchanged += _words(before_tokens[i1:i2])
            after_offset += len(after_text)
            continue

        before_text = "".join(before_tokens[i1:i2])
        removed += _words(before_tokens[i1:i2])
        added += _words(after_tokens[j1:j2])

        before_context = _context(before_tokens, i1, i2)[0]
        after_context = _context(after_tokens, j1, j2)[1]

        changes.append(Change(
            index=len(changes), kind=tag,
            before=before_text, after=after_text,
            before_context=before_context, after_context=after_context,
            anchor_start=after_offset, anchor_end=after_offset + len(after_text),
        ))
        after_offset += len(after_text)

    return Redline(changes=changes, added=added, removed=removed, unchanged=unchanged)


def apply(base: str, proposed: str, accepted: set[int] | list[int] | None) -> str:
    """Reconstruct the document with the accepted changes taken and the rest left as they were.

    Walks the same opcodes `compare` did, so the indices mean the same thing. Accepting every
    change yields `proposed` exactly; accepting none yields `base` exactly.
    """
    wanted = set(accepted or ())
    before_tokens = tokenise(base)
    after_tokens = tokenise(proposed)
    matcher = difflib.SequenceMatcher(None, before_tokens, after_tokens, autojunk=False)

    out: list[str] = []
    index = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.append("".join(before_tokens[i1:i2]))
            continue
        out.append("".join(after_tokens[j1:j2] if index in wanted else before_tokens[i1:i2]))
        index += 1

    return "".join(out)


def validate_selection(redline: Redline, accepted: list[int] | None) -> list[int]:
    """Reject indices that do not exist rather than silently ignoring them.

    A client sending a stale index is a client whose view of the document has drifted; applying
    the subset it *did* get right would produce a document nobody chose.
    """
    valid = {c.index for c in redline.changes}
    unknown = sorted(set(accepted or ()) - valid)
    if unknown:
        raise RedlineError(
            "These changes are not in this comparison (the document may have moved on): "
            + ", ".join(str(i) for i in unknown)
        )
    return sorted(set(accepted or ()))


def summarise(redline: Redline, *, accepted: list[int] | None = None) -> str:
    """A change-summary line for the version record. Reads as an audit entry, not a stat dump."""
    taken = len(set(accepted or ()))
    total = len(redline.changes)
    if not total:
        return "Redline applied with no changes"
    return (f"Redline: accepted {taken} of {total} change{'s' if total != 1 else ''} "
            f"(+{redline.added}/-{redline.removed} words)")
