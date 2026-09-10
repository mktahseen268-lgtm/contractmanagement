"""Merge fields — turn a structured form plus a pre-approved template into a draft.

This is the RFI's core intake mechanic (§2.3): a DFS POC picks an agreement type, fills a form
of drop-downs and lists-of-values, submits, and **the system generates the draft** by merging
the answers into the approved template. It is what replaces "email the legal team a Word file"
with something auditable, and it is why the template has a typed field schema rather than a
free-text body someone edits by hand each time.

Three properties this module exists to guarantee:

1. **Typed and validated server-side.** A `money` field that accepts "about 5 lakh" produces a
   contract nobody can report on. Validation happens here, not in the browser, because the
   browser is not the system of record.

2. **Unresolved placeholders are an error, never a blank.** If a template says
   `{{monthly_fee}}` and nothing supplies it, generating a contract with an empty space where
   the fee should be is far worse than refusing to generate. Silent blanks in an executed
   agreement are the failure mode this whole feature is meant to remove.

3. **Deterministic rendering.** The same values produce the same text, formatted identically
   in the internal document and in the DOCX export — so the Word file a counterparty receives
   says exactly what the record says.

Placeholder syntax is `{{field_key}}`, matching the convention already used by `pdf.py`.
Template fields take precedence over contract-derived variables, so a template can override
`{{counterparty}}` with a captured legal name.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field as dc_field

#: `{{ key }}` with optional whitespace. Keys are conservative on purpose — anything exotic is
#: more likely a typo than an intention.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z][a-zA-Z0-9_]{0,63})\s*\}\}")

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

FIELD_TYPES = (
    "text", "textarea", "number", "money", "date", "select", "multiselect",
    "boolean", "entity_ref", "file",
)

#: Types whose value is chosen from a list — the RFI's "drop-downs and LOVs".
CHOICE_TYPES = ("select", "multiselect")


class MergeError(ValueError):
    """The template definition or the submitted values are invalid. Routers map to 400."""


@dataclass
class FieldDef:
    key: str
    label: str = ""
    type: str = "text"
    required: bool = False
    options: list[str] = dc_field(default_factory=list)
    default: object = None
    help: str = ""
    group: str = ""
    #: For `entity_ref` — which kind of record this points at (`user`, `party`, `contract`).
    entity_kind: str = ""
    #: For `number` / `money`.
    minimum: float | None = None
    maximum: float | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> FieldDef:
        return cls(
            key=str(raw.get("key") or "").strip().lower(),
            label=str(raw.get("label") or "").strip(),
            type=str(raw.get("type") or "text").strip().lower(),
            required=bool(raw.get("required")),
            options=[str(o) for o in (raw.get("options") or [])],
            default=raw.get("default"),
            help=str(raw.get("help") or ""),
            group=str(raw.get("group") or ""),
            entity_kind=str(raw.get("entity_kind") or ""),
            minimum=_as_float(raw.get("minimum")),
            maximum=_as_float(raw.get("maximum")),
        )

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label or self.key.replace("_", " ").title(),
            "type": self.type, "required": self.required, "options": self.options,
            "default": self.default, "help": self.help, "group": self.group,
            "entity_kind": self.entity_kind, "minimum": self.minimum, "maximum": self.maximum,
        }


def _as_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_fields(raw: list | None) -> list[FieldDef]:
    return [FieldDef.from_dict(f) for f in (raw or []) if isinstance(f, dict)]


# ---------------------------------------------------------------------------------------
# Validating the template definition itself
# ---------------------------------------------------------------------------------------


def validate_definition(fields: list[FieldDef], body: str = "") -> list[str]:
    """Problems with the *template*, reported before anyone tries to use it.

    A broken template caught at authoring time costs a minute; caught at generation time it
    blocks whoever is trying to raise an agreement, usually under deadline.
    """
    problems: list[str] = []
    seen: set[str] = set()

    for index, f in enumerate(fields, start=1):
        where = f.label or f.key or f"field {index}"
        if not f.key:
            problems.append(f"{where}: every field needs a key.")
            continue
        if not _KEY_RE.match(f.key):
            problems.append(
                f"{where}: '{f.key}' is not a valid key — use lower-case letters, digits "
                "and underscores, starting with a letter."
            )
        if f.key in seen:
            problems.append(f"{where}: duplicate key '{f.key}'.")
        seen.add(f.key)
        if f.type not in FIELD_TYPES:
            problems.append(f"{where}: unknown field type '{f.type}'.")
        if f.type in CHOICE_TYPES and not f.options:
            problems.append(f"{where}: a {f.type} field needs at least one option.")
        if f.minimum is not None and f.maximum is not None and f.minimum > f.maximum:
            problems.append(f"{where}: the minimum is greater than the maximum.")

    if body:
        # A placeholder with no field behind it can never be filled — the template would
        # generate a contract with a literal `{{gap}}` in it, or worse, a silent blank.
        unknown = sorted(set(PLACEHOLDER_RE.findall(body)) - seen - set(_CONTRACT_KEYS))
        for key in unknown:
            problems.append(
                f"The template uses {{{{{key}}}}} but no field or contract value supplies it."
            )
    return problems


#: Keys `pdf.contract_variables` always provides. Kept here so `validate_definition` does not
#: flag them as unresolvable.
_CONTRACT_KEYS = (
    "counterparty", "our_entity", "org", "us", "title", "reference_no", "ref", "type",
    "value", "currency", "effective_date", "end_date", "governing_law", "renewal_type",
    "department", "status", "today",
)


# ---------------------------------------------------------------------------------------
# Validating submitted values
# ---------------------------------------------------------------------------------------


def _coerce(f: FieldDef, value) -> tuple[object, str | None]:
    """(cleaned value, error). Empty is handled by the caller so `required` reads in one place."""
    if f.type in ("text", "textarea"):
        return str(value).strip(), None

    if f.type in ("number", "money"):
        try:
            number = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None, f"{f.label or f.key} must be a number."
        if f.minimum is not None and number < f.minimum:
            return None, f"{f.label or f.key} must be at least {f.minimum:,.0f}."
        if f.maximum is not None and number > f.maximum:
            return None, f"{f.label or f.key} must be at most {f.maximum:,.0f}."
        return number, None

    if f.type == "date":
        if isinstance(value, dt.date):
            return value, None
        try:
            return dt.date.fromisoformat(str(value).strip()), None
        except ValueError:
            return None, f"{f.label or f.key} must be a date (YYYY-MM-DD)."

    if f.type == "boolean":
        if isinstance(value, bool):
            return value, None
        return str(value).strip().lower() in ("true", "yes", "1", "on"), None

    if f.type == "select":
        text = str(value).strip()
        if text not in f.options:
            return None, (
                f"{f.label or f.key}: '{text}' is not one of the permitted values "
                f"({', '.join(f.options)})."
            )
        return text, None

    if f.type == "multiselect":
        values = value if isinstance(value, list) else [value]
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        invalid = [v for v in cleaned if v not in f.options]
        if invalid:
            return None, (
                f"{f.label or f.key}: {', '.join(invalid)} not permitted "
                f"({', '.join(f.options)})."
            )
        return cleaned, None

    # entity_ref and file are opaque ids; existence is the caller's business.
    return str(value).strip(), None


def validate_values(fields: list[FieldDef], values: dict) -> tuple[dict, list[str]]:
    """Clean and check the submitted form. Returns (cleaned, errors).

    Unknown keys are dropped rather than rejected: a template edited between rendering the
    form and submitting it should not throw away everything the user typed.
    """
    cleaned: dict = {}
    errors: list[str] = []
    values = values or {}

    for f in fields:
        raw = values.get(f.key, f.default)
        empty = raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []

        if empty:
            if f.required:
                errors.append(f"{f.label or f.key} is required.")
            else:
                cleaned[f.key] = [] if f.type == "multiselect" else ""
            continue

        value, error = _coerce(f, raw)
        if error:
            errors.append(error)
        else:
            cleaned[f.key] = value

    return cleaned, errors


# ---------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------


def format_value(f: FieldDef | None, value, *, currency: str = "") -> str:
    """One value, formatted the same way everywhere it appears.

    Deterministic on purpose: the DOCX a counterparty receives must say exactly what the
    stored record says, down to the thousands separator.
    """
    if value is None or value == "":
        return ""
    kind = f.type if f is not None else "text"

    if kind == "money":
        try:
            return f"{currency + ' ' if currency else ''}{float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)
    if kind == "number":
        try:
            number = float(value)
            return f"{number:,.0f}" if number == int(number) else f"{number:,}"
        except (TypeError, ValueError):
            return str(value)
    if kind == "date" or isinstance(value, dt.date):
        day = value if isinstance(value, dt.date) else None
        if day is None:
            try:
                day = dt.date.fromisoformat(str(value))
            except ValueError:
                return str(value)
        return day.strftime("%d %B %Y")
    if kind == "boolean" or isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "multiselect" or isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


@dataclass
class RenderResult:
    text: str
    unresolved: list[str] = dc_field(default_factory=list)
    substituted: dict[str, str] = dc_field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.unresolved


def render(body: str, fields: list[FieldDef], values: dict, *,
           extra: dict | None = None, currency: str = "") -> RenderResult:
    """Substitute `{{key}}` throughout the body.

    Unresolved placeholders are **left in place and reported**, not blanked. A contract with a
    visible `{{monthly_fee}}` is an obvious defect; one with a silent gap where the fee should
    be is a defect that gets signed.
    """
    by_key = {f.key: f for f in fields}
    merged: dict[str, object] = dict(extra or {})
    merged.update(values or {})       # template fields win over contract-derived values

    substituted: dict[str, str] = {}
    unresolved: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in merged or merged[key] in (None, ""):
            if key not in unresolved:
                unresolved.append(key)
            return match.group(0)
        rendered = format_value(by_key.get(key), merged[key], currency=currency)
        if rendered == "":
            if key not in unresolved:
                unresolved.append(key)
            return match.group(0)
        substituted[key] = rendered
        return rendered

    return RenderResult(text=PLACEHOLDER_RE.sub(replace, body or ""),
                        unresolved=unresolved, substituted=substituted)


def jsonable(values: dict) -> dict:
    """Cleaned values as JSON-native types, for storing in the `merge_values` column.

    Dates become ISO strings. Nothing is lost: `format_value` parses an ISO string back to the
    same rendering, so a contract regenerated from stored values reads identically.
    """
    out: dict = {}
    for key, value in (values or {}).items():
        if isinstance(value, dt.date):
            out[key] = value.isoformat()
        elif isinstance(value, list):
            out[key] = [v.isoformat() if isinstance(v, dt.date) else v for v in value]
        else:
            out[key] = value
    return out


def placeholders_in(body: str) -> list[str]:
    """Every distinct placeholder a body uses, in first-appearance order."""
    seen: list[str] = []
    for key in PLACEHOLDER_RE.findall(body or ""):
        if key not in seen:
            seen.append(key)
    return seen


def suggest_fields(body: str, existing: list[FieldDef]) -> list[FieldDef]:
    """Field definitions for placeholders a template uses but has not defined.

    Authoring aid: paste a Word template full of `{{merchant_name}}`, get the form scaffolded
    rather than transcribing every placeholder by hand.
    """
    known = {f.key for f in existing} | set(_CONTRACT_KEYS)
    out: list[FieldDef] = []
    for key in placeholders_in(body):
        if key in known:
            continue
        known.add(key)
        guessed = "text"
        if key.endswith("_date") or key.startswith("date_"):
            guessed = "date"
        elif any(token in key for token in ("fee", "amount", "value", "price", "rate", "cost")):
            guessed = "money"
        elif any(token in key for token in ("count", "number", "qty", "quantity", "months", "days")):
            guessed = "number"
        out.append(FieldDef(key=key, label=key.replace("_", " ").title(), type=guessed))
    return out
