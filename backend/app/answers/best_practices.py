"""Best-practices knowledge for answering launch-site questions.

Per the spec, answers should follow best-practices for each platform, informed by
(a) the launch site's own guidance, (b) general community/blog wisdom, and
(c) the site's own page. Each site's registry entry already carries curated
``best_practices``; here we augment them with cross-platform heuristics and a
pluggable live-research hook (used when network + LLM are available).
"""
from __future__ import annotations

import logging

from ..models import LaunchSite

log = logging.getLogger(__name__)

# Cross-platform wisdom that applies to almost every launch directory.
GENERAL = [
    "Lead with the outcome for the user, not the technology.",
    "Keep the tagline to a single concrete sentence; avoid buzzwords.",
    "Use a clean, square logo that is legible at small sizes.",
    "Make sure the website link works and loads fast before submitting.",
    "Match the description length to the field limit; front-load the key message.",
]

# Tag-driven tips layered on top of the site's own best_practices.
_TAG_TIPS = {
    "pre-launch": "Frame the product as upcoming and emphasise the waitlist / early access.",
    "beta": "Be explicit that it's in beta and what early users get.",
    "developer-tools": "Speak to developers: stack, integrations, and whether it's open source.",
    "open-source": "Link the repository — these audiences reward and click do-follow OSS links.",
    "ai": "Be specific about what the AI does and the concrete benefit; avoid vague 'AI-powered'.",
    "seo": "Use keyword-rich, descriptive copy — the listing is a long-lived backlink.",
    "weekly-leaderboard": "Submit early in the cycle and rally first-day votes to rank.",
    "newsletter": "Open with a hook that reads well in a one-line newsletter blurb.",
    "alternatives": "Name the well-known products you are an alternative to, accurately.",
}


def get_best_practices(site: LaunchSite, researcher=None) -> list[str]:
    """Return a merged, de-duplicated best-practices list for a site."""
    tips: list[str] = list(site.best_practices)
    for tag in site.tags:
        tip = _TAG_TIPS.get(tag.lower())
        if tip and tip not in tips:
            tips.append(tip)
    for g in GENERAL:
        if g not in tips:
            tips.append(g)
    if researcher is not None:
        try:
            extra = researcher(site) or []
            for e in extra:
                if e not in tips:
                    tips.append(e)
        except Exception as exc:  # noqa: BLE001
            log.debug("best-practice research skipped for %s (%s)", site.id, exc)
    return tips


def live_researcher(provider, fetcher=None):
    """Build a researcher that reads the site's own page + asks the LLM for tips.

    Returns a callable ``(site) -> list[str]``. Used only when network + an LLM
    provider are available; otherwise the curated practices above are sufficient.
    """
    def _research(site: LaunchSite) -> list[str]:
        context = site.description
        if fetcher is not None:
            try:
                res = fetcher(site.url)
                context = (res.html or "")[:6000] or context
            except Exception:  # noqa: BLE001
                pass
        prompt = (
            f"From the following info about the launch platform '{site.name}', list 3 "
            f"concise, specific best-practices for submitting a software product there. "
            f"Return one tip per line, no numbering.\n\n{context}"
        )
        text = provider.complete(
            "You are an expert in product launches and directory submissions.", prompt
        )
        return [line.strip("-• ").strip() for line in text.splitlines() if line.strip()][:3]

    return _research
