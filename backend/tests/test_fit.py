"""Tests for smart length fitting (no mid-word truncation)."""
from app.answers.fit import fit_text


def test_no_change_when_within_limit():
    text, cut = fit_text("Short tagline", 60)
    assert text == "Short tagline"
    assert cut is False


def test_none_limit_passthrough():
    text, cut = fit_text("anything goes here", None)
    assert cut is False


def test_cuts_at_sentence_boundary():
    text, cut = fit_text("Plan sprints automatically. Ship faster every week.", 40)
    assert cut is True
    assert text == "Plan sprints automatically."
    assert len(text) <= 40


def test_cuts_at_clause_boundary_no_dangling_word():
    src = "AI task manager that plans your sprints, automates standups, and ships faster"
    text, cut = fit_text(src, 45)
    assert cut is True
    assert len(text) <= 45
    # ends cleanly on a clause, not a partial word
    assert not text.endswith(("an", "automat", "shi"))
    assert text == "AI task manager that plans your sprints"


def test_word_boundary_fallback_has_no_partial_token():
    src = "supercalifragilistic productivity platform for engineering teams everywhere"
    text, cut = fit_text(src, 30)
    assert cut is True
    assert len(text) <= 30
    assert " " not in text[-1:]  # no trailing space
    assert text.split()[-1] in src.split()  # last word is whole
