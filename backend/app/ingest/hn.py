"""Hacker News (Show HN) outcome ingestion via the public Algolia API.

`fetch_hn_outcome` takes an injectable ``fetcher(url) -> dict`` so it can be unit
-tested offline; the default fetcher uses httpx and is network-gated + guarded.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from ..models import LaunchOutcome

log = logging.getLogger(__name__)

_SEARCH = "https://hn.algolia.com/api/v1/search?tags=story&query={q}"


def _default_fetcher(url: str) -> dict:
    import httpx

    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def fetch_hn_outcome(query: str, fetcher=None, site_id: str = "showhn") -> LaunchOutcome | None:
    """Return a LaunchOutcome for the best-matching HN story, or None.

    ``query`` is typically the product name or the submission title.
    """
    fetcher = fetcher or _default_fetcher
    try:
        data = fetcher(_SEARCH.format(q=quote(query)))
    except Exception as exc:  # noqa: BLE001 - network-gated, degrade quietly
        log.debug("HN fetch failed for %r (%s)", query, exc)
        return None
    hits = (data or {}).get("hits") or []
    if not hits:
        return None
    best = max(hits, key=lambda h: h.get("points") or 0)
    return LaunchOutcome(
        site_id=site_id,
        status="live",
        points=best.get("points"),
        comments=best.get("num_comments"),
        notes=(best.get("title") or "")[:200],
        source="hn",
    )
