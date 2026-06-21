"""Smart length fitting for generated answers.

Instead of crudely chopping a too-long value mid-word, ``fit_text`` shortens at
the nearest sentence / clause / word boundary so the result reads as a complete
phrase that fits the platform's field limit. Returns ``(text, was_shortened)``.
"""
from __future__ import annotations

import re

_SENTENCE_ENDS = (". ", "! ", "? ")
_CLAUSE_SEPS = (" — ", " – ", " - ", "; ", ": ", ", ")
_TRAIL = " ,.;:—–-"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fit_text(text: str, max_length: int | None) -> tuple[str, bool]:
    """Shorten ``text`` to <= ``max_length`` at a natural boundary.

    The function never returns a dangling partial word. It only reports
    ``was_shortened=True`` when it actually had to drop content.
    """
    text = _clean(text)
    if not max_length or len(text) <= max_length:
        return text, False

    window = text[:max_length]
    floor = max(1, int(max_length * 0.5))  # don't shorten below ~half the limit

    # 1) Prefer ending on a complete sentence.
    for end in _SENTENCE_ENDS:
        idx = window.rfind(end)
        if idx >= floor:
            return window[: idx + 1].strip(), True

    # 2) Otherwise end on a clause boundary (dash, colon, semicolon, comma).
    for sep in _CLAUSE_SEPS:
        idx = window.rfind(sep)
        if idx >= floor:
            return window[:idx].strip().rstrip(_TRAIL), True

    # 3) Fall back to the last whole word.
    cut = window.rsplit(" ", 1)[0].strip().rstrip(_TRAIL)
    if not cut:  # single very long token
        cut = window.rstrip(_TRAIL)
    return cut, True
