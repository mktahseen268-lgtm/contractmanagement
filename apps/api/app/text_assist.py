"""Writing assistance for any text the product collects, served by a model inside the network.

Contract text, review notes, clause wording and obligation descriptions are all written by hand
under time pressure, and a typo in a clause is not a cosmetic problem — it is the thing the
counterparty's lawyer reads. This is the seam that offers a corrected version.

**Why there is no hosted option here.** Every other AI seam in this codebase ships a cloud
adapter beside the local one. This one does not, and the omission is deliberate: assistance
fires on the text as it is being typed, which means the *draft body of an agreement* would be
the payload. Sending that to a service outside Pakistan would contradict the data-residency
commitment the deployment is built around — a commitment the application enforces at boot by
refusing to start when a configured endpoint resolves outside the allowlist. A provider that
can only ever be wrong is better left unwritten than written and disabled.

So there are two providers:

* `DisabledTextAssist` — the default. Returns the text untouched and says so. Nothing in the
  product depends on assistance being available, and with no model configured the affordance
  simply does not appear.
* `LocalTextAssist` — an OpenAI-compatible endpoint on MMBL's own hardware (vLLM, Ollama, or
  anything else speaking `/chat/completions`). Set `TEXT_ASSIST_PROVIDER=local` and
  `TEXT_ASSIST_BASE_URL`.

The provider is asked to return the corrected text and nothing else. It is never asked to
decide anything: the result is shown beside the original for a human to accept or reject, and
an unaccepted suggestion changes nothing. That is what keeps this an assistant rather than an
unreviewed edit to a legal document.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .config import settings

log = logging.getLogger("cm.text_assist")

#: What the assistant may be asked to do. Each maps to an instruction below; anything else is
#: refused rather than passed through, so a caller cannot smuggle a free-text prompt to the
#: model through a field that looks like an enum.
MODES = ("correct", "formal", "shorten", "plain")

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


class TextAssistError(ValueError):
    """Raised for a bad request — an unknown mode, or text past the configured limit."""


class TextAssistProvider(ABC):
    name = "none"
    available = False

    @abstractmethod
    def assist(self, text: str, mode: str) -> dict:
        """Return `{"text": str, "changed": bool, "provider": str, "error": str}`.

        Never raises for a transport failure. A writing aid that takes the page down when the
        model is unreachable is worse than no writing aid, so failures come back as `error`
        with the original text intact and the caller shows the text unchanged.
        """


class DisabledTextAssist(TextAssistProvider):
    """The default. No model configured, so nothing is offered."""

    name = "disabled"
    available = False

    def assist(self, text: str, mode: str) -> dict:
        return {"text": text, "changed": False, "provider": self.name,
                "error": "No writing assistant is configured for this deployment."}


class LocalTextAssist(TextAssistProvider):
    """An OpenAI-compatible model hosted inside the deployment's own network.

    `urllib` rather than an SDK, matching the local OCR provider: the wire format is three JSON
    fields, and a dependency whose main contribution is a `base_url` parameter is a dependency
    to patch.
    """

    name = "local"
    available = True

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
                {"role": "system",
                 "content": _SYSTEM.format(instruction=_INSTRUCTIONS[mode])},
                {"role": "user", "content": text},
            ],
            # Zero temperature: the same sentence should correct the same way every time. A
            # writing aid that gives a different answer on a second press is one nobody trusts.
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
            return {"text": text, "changed": False, "provider": self.name,
                    "error": "The writing assistant is unavailable."}

        out = _unwrap(out)
        if not out:
            return {"text": text, "changed": False, "provider": self.name,
                    "error": "The assistant returned nothing usable."}
        return {"text": out, "changed": out != text, "provider": self.name, "error": ""}


def _unwrap(raw: str) -> str:
    """Strip the wrapping a chat model adds even when told not to.

    Models fence their output and open with "Here is the corrected text:" regardless of the
    instruction. Pasting that into a clause is worse than offering no suggestion, so it is
    removed here rather than trusted not to appear.
    """
    out = (raw or "").strip()
    if out.startswith("```"):
        parts = out.split("```")
        if len(parts) >= 2:
            out = parts[1]
            # A fence may carry a language tag on its first line.
            if "\n" in out and " " not in out.split("\n", 1)[0]:
                out = out.split("\n", 1)[1]
        out = out.strip()
    for lead in ("Here is the corrected text:", "Here's the corrected text:",
                 "Corrected text:", "Here is the revised text:", "Revised text:"):
        if out.lower().startswith(lead.lower()):
            out = out[len(lead):].strip()
    return out


def get_provider() -> TextAssistProvider:
    """The configured provider. `local` needs a base URL; anything short of that is disabled."""
    if settings.text_assist_provider == "local" and settings.text_assist_base_url:
        return LocalTextAssist(
            settings.text_assist_base_url,
            settings.text_assist_model,
            settings.text_assist_api_key,
            settings.text_assist_timeout_seconds,
        )
    return DisabledTextAssist()


def assist(text: str, mode: str) -> dict:
    """Validate the request, then hand it to the configured provider.

    The length cap is a real limit, not politeness: assistance is an interactive action, and a
    whole agreement body pushed through a model on a keystroke is a request that will time out
    on the user and occupy the worker while it does.
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
