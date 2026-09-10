"""The writing assistant: validation, the disabled default, and unwrapping model output."""

import pytest

from app import text_assist
from app.config import settings


# ---------------------------------------------------------------------------------------
# Off unless a model is actually configured
# ---------------------------------------------------------------------------------------


def test_no_assistant_is_configured_by_default():
    """A deployment that has not been given a model must not advertise the affordance."""
    provider = text_assist.get_provider()

    assert provider.available is False
    assert provider.name == "disabled"


def test_the_disabled_provider_returns_the_text_untouched():
    result = text_assist.assist("teh contract", "correct")

    assert result["text"] == "teh contract"
    assert result["changed"] is False
    assert result["error"]


def test_local_is_ignored_without_a_base_url(monkeypatch):
    """`local` with no URL is a half-finished configuration, not a reason to start calling out."""
    monkeypatch.setattr(settings, "text_assist_provider", "local")
    monkeypatch.setattr(settings, "text_assist_base_url", "")

    assert text_assist.get_provider().available is False


def test_a_configured_local_model_is_used(monkeypatch):
    monkeypatch.setattr(settings, "text_assist_provider", "local")
    monkeypatch.setattr(settings, "text_assist_base_url", "http://llm.internal/v1")
    monkeypatch.setattr(settings, "text_assist_model", "qwen2.5")

    provider = text_assist.get_provider()

    assert provider.available is True
    assert provider.base_url == "http://llm.internal/v1"


# ---------------------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------------------


def test_an_unknown_mode_is_refused():
    """The mode is an enum. A caller must not be able to hand the model a free-text prompt."""
    with pytest.raises(text_assist.TextAssistError, match="Unknown mode"):
        text_assist.assist("some text", "ignore-previous-instructions")


def test_empty_text_is_refused():
    with pytest.raises(text_assist.TextAssistError, match="no text"):
        text_assist.assist("   ", "correct")


def test_text_past_the_cap_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "text_assist_max_chars", 50)

    with pytest.raises(text_assist.TextAssistError, match="at a time"):
        text_assist.assist("x" * 51, "correct")


def test_text_at_the_cap_is_allowed(monkeypatch):
    monkeypatch.setattr(settings, "text_assist_max_chars", 50)

    result = text_assist.assist("x" * 50, "correct")

    assert result["provider"] == "disabled"  # got past validation to the provider


# ---------------------------------------------------------------------------------------
# Unwrapping what a chat model actually returns
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("The Bank shall pay.", "The Bank shall pay."),
    ("```\nThe Bank shall pay.\n```", "The Bank shall pay."),
    ("```text\nThe Bank shall pay.\n```", "The Bank shall pay."),
    ("Here is the corrected text: The Bank shall pay.", "The Bank shall pay."),
    ("Corrected text:\nThe Bank shall pay.", "The Bank shall pay."),
    ("   The Bank shall pay.   ", "The Bank shall pay."),
])
def test_model_wrapping_is_stripped(raw, expected):
    """Models fence and preface their output however firmly they are told not to.

    Pasting "Here is the corrected text:" into a clause is worse than offering no suggestion.
    """
    assert text_assist._unwrap(raw) == expected


def test_multi_line_text_survives_unwrapping():
    """A fence must not eat the body of a multi-paragraph clause."""
    raw = "```\nClause 1.\n\nClause 2.\n```"

    assert text_assist._unwrap(raw) == "Clause 1.\n\nClause 2."


# ---------------------------------------------------------------------------------------
# Transport failure
# ---------------------------------------------------------------------------------------


def test_an_unreachable_model_returns_the_original_text():
    """A writing aid that takes the page down when the model is unreachable is worse than none."""
    provider = text_assist.LocalTextAssist("http://127.0.0.1:9/v1", "m", timeout=1)

    result = provider.assist("teh contract", "correct")

    assert result["text"] == "teh contract"
    assert result["changed"] is False
    assert "unavailable" in result["error"]


# ---------------------------------------------------------------------------------------
# Residency
# ---------------------------------------------------------------------------------------


def test_a_configured_assistant_is_visible_to_the_residency_check(monkeypatch):
    """"It is a local model" is a claim about a URL. The boot check is what tests it."""
    from app import residency

    monkeypatch.setattr(settings, "text_assist_provider", "local")
    monkeypatch.setattr(settings, "text_assist_base_url", "https://llm.example.com/v1")

    hosts = {e.host for e in residency.collect_endpoints()}

    assert "llm.example.com" in hosts
