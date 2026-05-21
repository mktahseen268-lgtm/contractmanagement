"""OCR / AI extraction providers (RFI T-5 / docs/09).

The OCR subsystem is pluggable behind `OcrProvider`. Selection is config-driven
(`OCR_PROVIDER`):

  - `stub` (default)  — the deterministic, dependency-free demo extractor. Honest: it does NOT
                        read the document; it fabricates plausible fields seeded by file name.
                        Keeps dev + CI working with zero external services.
  - `anthropic`       — REAL extraction. Sends the actual uploaded PDF/image to Claude (which
                        reads scanned documents via vision) and asks for structured fields +
                        risk + clauses as JSON. Activates only when `OCR_API_KEY` is set and the
                        `anthropic` package is installed (see requirements-ai.txt).

All providers return the SAME result shape so the UI/`create-contract` flow is provider-agnostic:

    {
      "fields": { "<key>": {"value": ..., "confidence": 0..1}, ... },
      "risk_level": "low|medium|high|critical",
      "summary": "...",
      "detected_clauses": [...],
      "tables_found": int,
      "languages": [...],
      "pages": int,
      "provider": "stub|anthropic",
    }

Swapping to a different engine (Textract / Azure Document Intelligence / GPT-class) is a new
`OcrProvider` subclass + a branch in `get_ocr_provider()` — no caller changes.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import random
from abc import ABC, abstractmethod

from .config import settings

# Fields we ask any provider to populate. Kept here so the prompt + the stub agree on the schema.
EXTRACTION_FIELDS = ["title", "type", "counterparty", "effective_date", "end_date", "value", "currency", "renewal_type", "governing_law"]

_STUB_PARTIES = ["Acme Corporation", "Globex LLC", "Northstar Industries", "Initech FZE", "Stark Trading Co.", "Wayne Holdings"]
_STUB_TYPES = ["msa", "nda", "lease", "vendor", "service"]
_TITLE = {"msa": "Master Services Agreement", "nda": "Mutual Non-Disclosure Agreement", "lease": "Office Lease Agreement", "vendor": "Vendor Agreement", "service": "Service Agreement"}


class OcrProvider(ABC):
    name: str

    @abstractmethod
    def extract(self, *, file_bytes: bytes | None, file_name: str, content_type: str = "") -> dict:
        """Run OCR+extraction. `file_bytes` may be None (stub ignores it). Returns the result dict."""
        raise NotImplementedError


# ---------------------------------------------------------------- stub (default) ----


def build_extraction(file_name: str) -> dict:
    """A plausible OCR+AI extraction result, deterministic per file name. Demo-only — does not
    read the document. (Kept here so `ocr_provider` is the single home for extraction logic.)"""
    rng = random.Random(file_name)
    party = rng.choice(_STUB_PARTIES)
    ctype = rng.choice(_STUB_TYPES)
    start = dt.date.today() - dt.timedelta(days=rng.randint(0, 120))
    months = rng.choice([12, 24, 36])
    end = start + dt.timedelta(days=months * 30)
    value = rng.choice([24000, 48000, 96000, 120000, 250000])
    risk = rng.choice(["low", "low", "medium", "high"])
    title = f"{_TITLE[ctype]} — {party}"
    return {
        "fields": {
            "title": {"value": title, "confidence": round(rng.uniform(0.88, 0.97), 2)},
            "type": {"value": ctype, "confidence": round(rng.uniform(0.9, 0.98), 2)},
            "counterparty": {"value": party, "confidence": round(rng.uniform(0.85, 0.96), 2)},
            "effective_date": {"value": start.isoformat(), "confidence": round(rng.uniform(0.6, 0.95), 2)},
            "end_date": {"value": end.isoformat(), "confidence": round(rng.uniform(0.45, 0.92), 2)},
            "value": {"value": value, "confidence": round(rng.uniform(0.8, 0.95), 2)},
            "currency": {"value": "USD", "confidence": 0.99},
            "renewal_type": {"value": rng.choice(["none", "auto", "manual"]), "confidence": round(rng.uniform(0.6, 0.9), 2)},
            "governing_law": {"value": rng.choice(["Oman", "UAE", "Saudi Arabia", "England & Wales"]), "confidence": round(rng.uniform(0.7, 0.93), 2)},
        },
        "risk_level": risk,
        "summary": f"{months}-month {_TITLE[ctype].lower()} with {party}. Standard commercial terms; governing law as detected. (AI summary — verify before relying.)",
        "detected_clauses": rng.sample(["Confidentiality", "Limitation of Liability", "Termination", "Indemnification", "Governing Law", "Force Majeure", "IP Ownership", "Data Protection", "Payment Terms"], k=rng.randint(5, 8)),
        "tables_found": rng.randint(0, 2),
        "languages": ["en"] + (["ar"] if rng.random() < 0.3 else []),
        "pages": rng.randint(2, 14),
        "provider": "stub",
    }


class StubOcrProvider(OcrProvider):
    name = "stub"

    def extract(self, *, file_bytes: bytes | None, file_name: str, content_type: str = "") -> dict:
        return build_extraction(file_name)


# ---------------------------------------------------------------- anthropic (real) ----

_EXTRACTION_PROMPT = (
    "You are a contract-analysis engine. Read the attached document and extract the following as "
    "strict JSON (no prose, no markdown fences). Schema:\n"
    "{\n"
    '  "fields": {\n'
    '    "title": {"value": string, "confidence": number 0..1},\n'
    '    "type": {"value": one of ["nda","msa","lease","employment","vendor","service","other"], "confidence": number},\n'
    '    "counterparty": {"value": string, "confidence": number},\n'
    '    "effective_date": {"value": "YYYY-MM-DD" or "", "confidence": number},\n'
    '    "end_date": {"value": "YYYY-MM-DD" or "", "confidence": number},\n'
    '    "value": {"value": number, "confidence": number},\n'
    '    "currency": {"value": ISO-4217 string, "confidence": number},\n'
    '    "renewal_type": {"value": one of ["none","auto","manual"], "confidence": number},\n'
    '    "governing_law": {"value": string, "confidence": number}\n'
    "  },\n"
    '  "risk_level": one of ["low","medium","high","critical"],\n'
    '  "summary": string (2-3 sentences),\n'
    '  "detected_clauses": string[],\n'
    '  "tables_found": number,\n'
    '  "languages": string[] (ISO codes),\n'
    '  "pages": number\n'
    "}\n"
    "Use confidence to reflect how clearly each field was stated. If a field is absent, set value "
    'to "" (or 0) and a low confidence. Return ONLY the JSON object.'
)


class AnthropicOcrProvider(OcrProvider):
    """Real OCR+extraction via Claude. Claude reads the document directly (PDF document block or
    image block — handles scanned files via vision), so this is true OCR+AI, not text-only."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_pages: int = 20) -> None:
        self.api_key = api_key
        self.model = model
        self.max_pages = max_pages

    def extract(self, *, file_bytes: bytes | None, file_name: str, content_type: str = "") -> dict:
        if not file_bytes:
            raise RuntimeError("anthropic OCR needs the uploaded file bytes (none were provided).")
        try:
            import anthropic  # optional dep — see requirements-ai.txt
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("OCR_PROVIDER=anthropic but the `anthropic` package isn't installed (pip install -r requirements-ai.txt).") from e

        client = anthropic.Anthropic(api_key=self.api_key)
        b64 = base64.standard_b64encode(file_bytes).decode("ascii")
        ctype = (content_type or "").lower()
        if "pdf" in ctype or file_name.lower().endswith(".pdf"):
            doc_block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
        else:
            media = "image/png" if file_name.lower().endswith(".png") else "image/jpeg"
            doc_block = {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}}

        resp = client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": [doc_block, {"type": "text", "text": _EXTRACTION_PROMPT}]}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text").strip()
        result = _parse_json_object(text)
        result.setdefault("languages", ["en"])
        result.setdefault("tables_found", 0)
        result.setdefault("detected_clauses", [])
        result.setdefault("risk_level", "low")
        result["provider"] = "anthropic"
        return result


def _parse_json_object(text: str) -> dict:
    """Best-effort parse of a JSON object from the model's reply (strips stray fences/prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("OCR provider returned a non-JSON response.")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------- factory ----


def get_ocr_provider() -> OcrProvider:
    """Pick the provider from config. Falls back to the stub when the cloud provider isn't fully
    configured, so the app always works (it just won't read the document for real)."""
    if settings.ocr_provider == "anthropic" and settings.ocr_api_key:
        return AnthropicOcrProvider(settings.ocr_api_key, settings.ocr_model, settings.ocr_max_pages)
    return StubOcrProvider()
