"""The writing assistant: the built-in checker, provider selection, and validation."""

import pytest

from app import text_assist
from app.config import settings


# ---------------------------------------------------------------------------------------
# Which provider is in play
# ---------------------------------------------------------------------------------------


def test_the_builtin_checker_is_the_default():
    """Spelling and punctuation must work on a deployment with no model and no network."""
    provider = text_assist.get_provider()

    assert provider.available is True
    assert provider.name == "builtin"


def test_the_builtin_checker_does_not_claim_to_rephrase():
    """Rephrasing needs judgement. Offering it without a model would be guesswork on a clause."""
    assert text_assist.get_provider().modes == ("correct",)


def test_the_feature_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "text_assist_provider", "none")

    assert text_assist.get_provider().available is False


def test_local_is_ignored_without_a_base_url(monkeypatch):
    """`local` with no URL is a half-finished configuration, not a reason to start calling out."""
    monkeypatch.setattr(settings, "text_assist_provider", "local")
    monkeypatch.setattr(settings, "text_assist_base_url", "")

    assert text_assist.get_provider().name == "builtin"


def test_a_configured_local_model_is_used(monkeypatch):
    monkeypatch.setattr(settings, "text_assist_provider", "local")
    monkeypatch.setattr(settings, "text_assist_base_url", "http://llm.internal/v1")
    monkeypatch.setattr(settings, "text_assist_model", "qwen2.5")

    provider = text_assist.get_provider()

    assert provider.name == "local"
    assert provider.modes == text_assist.MODES


# ---------------------------------------------------------------------------------------
# Spelling
# ---------------------------------------------------------------------------------------


def test_a_misspelling_is_corrected():
    result = text_assist.assist("The Bank shall recieve the paymnet.", "correct")

    assert "receive" in result["text"]
    assert "payment" in result["text"]
    assert result["changed"] is True


def test_the_correction_says_what_it_changed():
    """A checker that silently rewrites teaches nothing and earns no trust."""
    result = text_assist.assist("The Bank shall recieve it.", "correct")

    assert any("recieve" in n and "receive" in n for n in result["notes"])


def test_capitalisation_is_preserved():
    """`Teh` is a typo at the start of a sentence; `THE` is a heading."""
    assert "Their" in text_assist.assist("Thier duty is clear.", "correct")["text"]
    assert "RECEIVE" in text_assist.assist("SHALL RECIEVE NOW.", "correct")["text"]


def test_correct_text_is_left_alone():
    original = "The Bank shall receive the payment within thirty days."

    result = text_assist.assist(original, "correct")

    assert result["text"] == original
    assert result["changed"] is False


def test_a_party_name_is_not_mangled():
    """The list is curated precisely so names and defined terms survive untouched."""
    original = "Mobilink Microfinance Bank and Margalla Technologies agree as follows."

    assert text_assist.assist(original, "correct")["text"] == original


# ---------------------------------------------------------------------------------------
# Sentences and punctuation
# ---------------------------------------------------------------------------------------


def test_a_repeated_word_is_removed():
    result = text_assist.assist("The the Bank shall pay.", "correct")

    assert result["text"] == "The Bank shall pay."


def test_a_space_before_a_comma_is_closed_up():
    result = text_assist.assist("The Bank , at its discretion , may pay.", "correct")

    assert " ," not in result["text"]


def test_a_missing_space_after_a_comma_is_added():
    result = text_assist.assist("The Bank,at its discretion,may pay.", "correct")

    assert "Bank, at" in result["text"]


def test_a_sentence_start_is_capitalised():
    result = text_assist.assist("the Bank shall pay. the Client shall not.", "correct")

    assert result["text"].startswith("The Bank")
    assert "The Client" in result["text"]


def test_a_long_sentence_is_flagged_not_split():
    """Splitting a clause changes what it means, so this is guidance and never an edit."""
    long_one = "The Bank shall pay " + " and ".join(["the agreed amount"] * 20) + "."

    result = text_assist.assist(long_one, "correct")

    assert any("consider splitting" in n for n in result["notes"])
    # Still one sentence: the checker reported the problem, it did not solve it by cutting.
    assert result["text"].count(".") == 1


def test_a_missing_full_stop_is_reported_not_added():
    """Where the author was going is a guess, so it is raised rather than assumed."""
    result = text_assist.assist("The Bank shall pay the agreed amount", "correct")

    assert any("full stop" in n for n in result["notes"])
    assert result["text"].endswith("amount")


def test_clean_text_says_so():
    result = text_assist.assist("The Bank shall pay the agreed amount.", "correct")

    assert any("No spelling or punctuation problems" in n for n in result["notes"])


def test_rephrasing_without_a_model_is_refused_clearly():
    result = text_assist.assist("The Bank shall pay.", "formal")

    assert result["changed"] is False
    assert "language model" in result["error"]


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

    assert result["provider"] == "builtin"  # got past validation to the provider


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


def test_an_unreachable_model_falls_back_to_the_builtin_checks():
    """An unreachable model should cost the rephrasing, not the spellcheck."""
    provider = text_assist.LocalTextAssist("http://127.0.0.1:9/v1", "m", timeout=1)

    result = provider.assist("teh contract", "correct")

    assert result["text"] == "The contract"
    assert result["provider"] == "builtin"
    assert any("unreachable" in n for n in result["notes"])


def test_an_unreachable_model_cannot_fake_a_rephrase():
    """There is no deterministic fallback for "make it formal", so it says so."""
    provider = text_assist.LocalTextAssist("http://127.0.0.1:9/v1", "m", timeout=1)

    result = provider.assist("the contract", "formal")

    assert result["text"] == "the contract"
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
