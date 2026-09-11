"""Writing assistance for any text the product collects.

Contract text, review notes, clause wording and obligation descriptions are all written by hand
under time pressure, and a typo in a clause is not cosmetic — it is the thing the counterparty's
lawyer reads.

Three providers, in increasing order of capability:

* `BuiltinTextAssist` — **the default, and it needs nothing installed.** Deterministic spelling
  and sentence checks: a curated misspelling list weighted towards the words this domain
  actually gets wrong, doubled words, spacing and punctuation slips, and a warning on sentences
  long enough to lose a reader. It reports *what* it changed, so it teaches rather than silently
  rewriting.
* `LocalTextAssist` — an OpenAI-compatible model on MMBL's own hardware (vLLM, Ollama, or
  anything speaking `/chat/completions`). Adds rephrasing: formal register, concision, plain
  language. Set `TEXT_ASSIST_PROVIDER=local` and `TEXT_ASSIST_BASE_URL`.
* `DisabledTextAssist` — explicit opt-out via `TEXT_ASSIST_PROVIDER=none`.

**Why there is no hosted option.** Every other AI seam here ships a cloud adapter beside the
local one. This one does not, deliberately: assistance fires on text as it is being typed, so
the payload is the *draft body of an agreement*. Sending that outside Pakistan would contradict
the data-residency commitment the deployment is built around — one the application enforces at
boot by refusing to start when a configured endpoint resolves outside the allowlist.

Nothing here decides anything. The result is shown beside the original for a human to accept or
reject, and an unaccepted suggestion changes nothing.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from .config import settings

log = logging.getLogger("cm.text_assist")

#: Everything a provider may be asked to do. A closed set, so a caller cannot smuggle a
#: free-text prompt to a model through a field that looks like a dropdown.
MODES = ("correct", "formal", "shorten", "plain")

#: What the built-in checker can do on its own. Rephrasing needs a model.
BUILTIN_MODES = ("correct",)

_INSTRUCTIONS = {
    "correct": (
        "Correct spelling, grammar and punctuation. Keep the author's wording, tone and "
        "meaning exactly as they are. Do not rephrase, do not add or remove clauses, do not "
        "change numbers, dates, party names or defined terms. If the text is already correct, "
        "return it unchanged."
    ),
    "formal": (
        "Rewrite in the register of a formal banking agreement. Preserve every fact, number, "
        "date, party name and obligation exactly. Do not introduce new terms or commitments."
    ),
    "shorten": (
        "Make this more concise without losing any obligation, condition, number or date. "
        "Removing meaning is a failure; removing words is the goal."
    ),
    "plain": (
        "Rewrite in plain language a non-lawyer can follow, keeping every obligation, number "
        "and date intact. Do not soften or drop any requirement."
    ),
}

_SYSTEM = (
    "You are an editing assistant working on contract and business text for a bank. "
    "{instruction}\n\n"
    "Reply with the resulting text and nothing else — no preamble, no explanation, no quotes "
    "around it, no markdown fence. Never invent a fact that is not in the input."
)

#: Misspellings worth correcting, weighted towards this domain. Deliberately a curated list
#: rather than a dictionary: a general speller flags every party name, defined term and
#: abbreviation in an agreement, and a checker that cries wolf on "Mobilink" gets switched off.
#: Keys are lower-case; the replacement's capitalisation is matched to the original.
_MISSPELLINGS = {
    # General business prose
    "recieve": "receive", "recieved": "received", "seperate": "separate",
    "seperately": "separately", "occured": "occurred", "occuring": "occurring",
    "accomodate": "accommodate", "acknowledgment": "acknowledgement",
    "agreeement": "agreement", "aggreement": "agreement", "agreemnt": "agreement",
    "cancelation": "cancellation", "commited": "committed", "comitted": "committed",
    "definately": "definitely", "occassion": "occasion", "priviledge": "privilege",
    "reccomend": "recommend", "recomend": "recommend", "refered": "referred",
    "relevent": "relevant", "responsability": "responsibility", "succesful": "successful",
    "sucessful": "successful", "untill": "until", "wich": "which", "teh": "the",
    "adn": "and", "thier": "their", "recipt": "receipt", "buisness": "business",
    "goverment": "government", "enviroment": "environment", "maintainance": "maintenance",
    "maintenence": "maintenance", "neccessary": "necessary", "necesary": "necessary",
    "paymnet": "payment", "paymetn": "payment", "invoicce": "invoice",
    # Contract and banking vocabulary
    "indemnitee": "indemnitee", "indeminty": "indemnity", "indemnify": "indemnify",
    "indeminfy": "indemnify", "liabilty": "liability", "liablity": "liability",
    "confidentiallity": "confidentiality", "confidentialty": "confidentiality",
    "juridiction": "jurisdiction", "jurisdication": "jurisdiction",
    "termintation": "termination", "terminaton": "termination",
    "warrenty": "warranty", "warrranty": "warranty", "breech": "breach",
    "clauses": "clauses", "clasue": "clause", "cluase": "clause",
    "signatary": "signatory", "signitory": "signatory", "counterpary": "counterparty",
    "counterparyt": "counterparty", "amendmend": "amendment", "ammendment": "amendment",
    "renewel": "renewal", "renewl": "renewal", "obligaton": "obligation",
    "obligatoin": "obligation", "complaince": "compliance", "complience": "compliance",
    "regulatary": "regulatory", "regualtory": "regulatory", "colateral": "collateral",
    "disbursment": "disbursement", "remitance": "remittance", "guarentee": "guarantee",
    "gaurantee": "guarantee", "morgage": "mortgage", "finacial": "financial",
    "finiancial": "financial", "instalment": "instalment", "settlment": "settlement",
}

#: A sentence past this many words is usually two sentences. Flagged, never split
#: automatically: splitting a clause changes what it means.
_LONG_SENTENCE_WORDS = 45


class TextAssistError(ValueError):
    """A bad request — an unknown mode, empty text, or past the configured limit."""


class TextAssistProvider(ABC):
    name = "none"
    available = False
    modes: tuple[str, ...] = ()

    @abstractmethod
    def assist(self, text: str, mode: str) -> dict:
        """Return `{"text", "changed", "notes", "provider", "error"}`.

        Never raises for a transport failure. A writing aid that takes the page down when the
        model is unreachable is worse than no writing aid, so failures come back as `error`
        with the original text intact.
        """


class DisabledTextAssist(TextAssistProvider):
    """Explicitly switched off for this deployment."""

    name = "disabled"
    available = False

    def assist(self, text: str, mode: str) -> dict:
        return {"text": text, "changed": False, "notes": [], "provider": self.name,
                "error": "The writing assistant is switched off for this deployment."}


def _match_case(original: str, replacement: str) -> str:
    """Keep the author's capitalisation: Teh -> The, TEH -> THE."""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


class BuiltinTextAssist(TextAssistProvider):
    """Spelling and sentence checks with no model and no network.

    Every rule here is deterministic and reversible, because the author sees the result before
    it is applied and has to be able to tell at a glance what happened to their words. Nothing
    in this class rephrases: the moment a checker starts rewriting sentences it needs judgement,
    and judgement without a model is guesswork on a legal document.
    """

    name = "builtin"
    available = True
    modes = BUILTIN_MODES

    def assist(self, text: str, mode: str) -> dict:
        if mode not in self.modes:
            return {
                "text": text, "changed": False, "notes": [], "provider": self.name,
                "error": ("Rephrasing needs a language model. Spelling and punctuation "
                          "checking works without one."),
            }

        out = text
        notes: list[str] = []

        # --- spelling -------------------------------------------------------------------
        fixed: list[str] = []

        def spell(m: re.Match) -> str:
            word = m.group(0)
            replacement = _MISSPELLINGS.get(word.lower())
            if not replacement or replacement.lower() == word.lower():
                return word
            fixed.append(f"{word} → {_match_case(word, replacement)}")
            return _match_case(word, replacement)

        out = re.sub(r"\b[A-Za-z]+\b", spell, out)
        if fixed:
            notes.append("Spelling: " + ", ".join(sorted(set(fixed))[:8]))

        # --- doubled words --------------------------------------------------------------
        doubled: list[str] = []

        def dedupe(m: re.Match) -> str:
            doubled.append(m.group(1))
            return m.group(1)

        # Only across a plain space, so "had had" spanning a line break is left alone.
        out, n = re.subn(r"\b(\w+)( +)\1\b", dedupe, out, flags=re.IGNORECASE)
        if n:
            notes.append(f"Removed a repeated word: {', '.join(sorted(set(doubled))[:5])}")

        # --- spacing and punctuation ------------------------------------------------------
        before = out
        # A space before a comma or full stop, and a missing one after.
        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", out)
        # A full stop followed immediately by a letter, but not inside a decimal or an
        # abbreviation like "e.g." — those are single letters either side.
        out = re.sub(r"(?<=[a-z]{2})\.(?=[A-Z])", ". ", out)
        # Runs of spaces, but never leading indentation, which may be deliberate in a clause.
        out = re.sub(r"(?<=\S)  +", " ", out)
        if out != before:
            notes.append("Tidied spacing around punctuation.")

        # --- sentence starts ----------------------------------------------------------------
        before = out
        out = re.sub(r"(^|[.!?]\s+)([a-z])",
                     lambda m: m.group(1) + m.group(2).upper(), out)
        if out != before:
            notes.append("Capitalised the start of a sentence.")

        # --- guidance, not edits -------------------------------------------------------------
        # Reported rather than applied: splitting a clause changes what it means, and adding a
        # full stop to an unfinished sentence guesses where the author was going.
        for sentence in re.split(r"(?<=[.!?])\s+", out):
            words = len(sentence.split())
            if words > _LONG_SENTENCE_WORDS:
                notes.append(
                    f"One sentence runs to {words} words — consider splitting it: "
                    f"“{sentence.strip()[:60]}…”"
                )
                break

        stripped = out.strip()
        if stripped and stripped[-1] not in ".!?:;" and len(stripped.split()) > 3:
            notes.append("The text does not end in a full stop.")

        if not notes:
            notes.append("No spelling or punctuation problems found.")

        return {"text": out, "changed": out != text, "notes": notes,
                "provider": self.name, "error": ""}


class LocalTextAssist(TextAssistProvider):
    """An OpenAI-compatible model hosted inside the deployment's own network.

    `urllib` rather than an SDK, matching the local OCR provider: the wire format is three JSON
    fields, and a dependency whose main contribution is a `base_url` parameter is one to patch.
    """

    name = "local"
    available = True
    modes = MODES

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def assist(self, text: str, mode: str) -> dict:
        import json
        import urllib.request

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM.format(instruction=_INSTRUCTIONS[mode])},
                {"role": "user", "content": text},
            ],
            # Zero temperature: the same sentence should correct the same way every time. An
            # aid that gives a different answer on a second press is one nobody trusts.
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
            out = body["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — every transport failure is the same here
            log.warning("local text assistant failed: %s", e)
            # Fall back to the deterministic checks rather than leaving the author with
            # nothing: an unreachable model should cost the rephrasing, not the spellcheck.
            if mode == "correct":
                result = BuiltinTextAssist().assist(text, mode)
                result["notes"].append("The language model was unreachable; "
                                       "checked with the built-in rules instead.")
                return result
            return {"text": text, "changed": False, "notes": [], "provider": self.name,
                    "error": "The writing assistant is unavailable."}

        out = _unwrap(out)
        if not out:
            return {"text": text, "changed": False, "notes": [], "provider": self.name,
                    "error": "The assistant returned nothing usable."}
        return {"text": out, "changed": out != text, "notes": [], "provider": self.name,
                "error": ""}


def _unwrap(raw: str) -> str:
    """Strip the wrapping a chat model adds even when told not to.

    Models fence their output and open with "Here is the corrected text:" regardless of the
    instruction. Pasting that into a clause is worse than offering no suggestion.
    """
    out = (raw or "").strip()
    if out.startswith("```"):
        parts = out.split("```")
        if len(parts) >= 2:
            out = parts[1]
            if "\n" in out and " " not in out.split("\n", 1)[0]:
                out = out.split("\n", 1)[1]
        out = out.strip()
    for lead in ("Here is the corrected text:", "Here's the corrected text:",
                 "Corrected text:", "Here is the revised text:", "Revised text:"):
        if out.lower().startswith(lead.lower()):
            out = out[len(lead):].strip()
    return out


def get_provider() -> TextAssistProvider:
    """The configured provider. `local` needs a base URL; `none` switches the feature off."""
    if settings.text_assist_provider == "local" and settings.text_assist_base_url:
        return LocalTextAssist(
            settings.text_assist_base_url,
            settings.text_assist_model,
            settings.text_assist_api_key,
            settings.text_assist_timeout_seconds,
        )
    if settings.text_assist_provider == "none":
        return DisabledTextAssist()
    return BuiltinTextAssist()


def assist(text: str, mode: str) -> dict:
    """Validate the request, then hand it to the configured provider.

    The length cap is a real limit, not politeness: assistance is interactive, and a whole
    agreement body pushed through a model on a keystroke is a request that will time out on the
    user and occupy the worker while it does.
    """
    if mode not in MODES:
        raise TextAssistError(f"Unknown mode {mode!r}. Expected one of: {', '.join(MODES)}.")

    body = (text or "").strip()
    if not body:
        raise TextAssistError("There is no text to work on.")
    if len(body) > settings.text_assist_max_chars:
        raise TextAssistError(
            f"That is {len(body):,} characters; the assistant handles up to "
            f"{settings.text_assist_max_chars:,} at a time. Select a smaller passage."
        )

    return get_provider().assist(body, mode)
