"""Deterministic heuristic analyzer used when no OpenAI key is available.

This is intentionally *not* a stub: it performs real extraction over the scanned
page structure so the end-to-end product works (and is testable) offline. When an
OpenAI key is present, OpenAIProvider supersedes this with higher-quality output.
"""
from __future__ import annotations

import re
from collections import Counter

from ..models import LaunchSite, Product, Question, ScannedPage
from .base import LLMProvider

# Keyword → category/tag taxonomy for lightweight classification.
_CATEGORY_KEYWORDS = {
    "AI": ["ai", "artificial intelligence", "llm", "gpt", "machine learning", "ml ", "agent"],
    "SaaS": ["saas", "subscription", "cloud platform", "web app", "dashboard"],
    "Developer Tools": ["developer", "api", "sdk", "cli", "open source", "framework", "library", "code"],
    "Productivity": ["productivity", "workflow", "automation", "task", "notes", "calendar"],
    "Marketing": ["marketing", "seo", "campaign", "growth", "leads", "audience"],
    "Analytics": ["analytics", "metrics", "insights", "tracking", "data"],
    "Design": ["design", "ui", "ux", "figma", "prototype", "wireframe"],
    "No-Code": ["no-code", "no code", "drag and drop", "builder"],
    "Fintech": ["payment", "invoice", "billing", "fintech", "finance", "crypto"],
    "Security": ["security", "encryption", "privacy", "compliance", "auth"],
}

_ICP_HINTS = [
    (r"for developers|for engineers|developer tools|api[s]?\b", "Software developers and engineering teams"),
    (r"for marketers|marketing teams|growth teams", "Marketers and growth teams"),
    (r"for designers|design teams", "Designers and product teams"),
    (r"for startups|founders|indie hackers|makers", "Startup founders, indie hackers and makers"),
    (r"for teams|for businesses|enterprise|b2b", "Teams and businesses (B2B)"),
    (r"for creators|content creators|writers", "Content creators and writers"),
    (r"for sales|sales teams|crm", "Sales teams"),
]

_BENEFIT_CUES = re.compile(
    r"\b(save[s]? (time|money)|faster|automate|increase|boost|reduce|effortless|"
    r"instantly|in seconds|no more|without|easily|seamless|10x|grow|scale)\b",
    re.I,
)

_FEATURE_HEADING = re.compile(r"feature|capabilit|what you|how it works|benefits", re.I)
_TITLE_SUFFIX = re.compile(r"\s*[\|\-–—:·»]\s*")
_GENERIC_TITLE = re.compile(r"^(home|homepage|welcome|index|loading)$", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", _clean(text))
    return [p.strip() for p in parts if len(p.strip()) > 3]


class MockProvider(LLMProvider):
    name = "mock"

    # -- public API --------------------------------------------------------
    def analyze_product(self, url: str, pages: list[ScannedPage]) -> dict:
        home = pages[0] if pages else ScannedPage(url=url)
        all_text = " ".join(p.text for p in pages)
        lower = all_text.lower()

        name = self._name(home, url)
        tagline = self._tagline(home)
        desc_short = self._desc_short(home, tagline)
        desc_long = self._desc_long(pages, desc_short)
        categories = self._categories(lower)
        tags = self._tags(lower, categories)
        features = self._features(pages)
        benefits = self._benefits(pages)
        icp = self._icp(lower)
        target = icp
        positioning = self._positioning(name, tagline, categories)
        pricing = self._pricing(lower)
        social = self._social_links(pages)

        return {
            "name": name,
            "tagline": tagline,
            "description_short": desc_short,
            "description_long": desc_long,
            "positioning": positioning,
            "icp": icp,
            "target_group": target,
            "categories": categories,
            "topics_tags": tags,
            "features": features,
            "benefits": benefits,
            "pricing": pricing,
            "social_links": social,
        }

    def generate_answer(
        self,
        *,
        question: Question,
        product: Product,
        site: LaunchSite,
        best_practices: list[str],
    ) -> str:
        value = self._value_for(question, product, site)
        value = _clean(value)
        if question.max_length and len(value) > question.max_length:
            value = value[: question.max_length].rsplit(" ", 1)[0].rstrip(",.;:")
        return value

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        # Deterministic: return the first few sentences of the user content.
        return " ".join(_sentences(user)[:3])

    # -- field mapping for answers ----------------------------------------
    def _value_for(self, q: Question, p: Product, site: LaunchSite) -> str:
        mapping = {
            "name": p.name,
            "tagline": p.tagline,
            "description_short": p.description_short,
            "description_long": p.description_long or p.description_short,
            "positioning": p.positioning,
            "icp": p.icp,
            "target_group": p.target_group,
            "pricing": p.pricing or "Free",
            "url": p.canonical_url or p.url,
            "maker_name": p.maker_name,
            "maker_email": p.maker_email,
        }
        if q.maps_to in mapping and mapping[q.maps_to]:
            return mapping[q.maps_to]
        if q.maps_to == "categories":
            return ", ".join(p.categories[:3])
        if q.maps_to == "topics_tags":
            return ", ".join(p.topics_tags[:5])
        if q.maps_to == "features":
            return "; ".join(f.title for f in p.features[:5])
        if q.maps_to == "benefits":
            return " ".join(p.benefits[:3])
        if q.maps_to in {"twitter", "github", "linkedin"}:
            return p.social_links.get(q.maps_to, "")
        # Sensible fallbacks by field type / id.
        if q.type == "url":
            return p.canonical_url or p.url
        if q.type == "email":
            return p.maker_email
        if "tagline" in q.id or "pitch" in q.id:
            return p.tagline
        if "desc" in q.id:
            return p.description_long or p.description_short
        return ""

    # -- heuristics --------------------------------------------------------
    def _name(self, home: ScannedPage, url: str) -> str:
        if home.og.get("site_name"):
            return _clean(home.og["site_name"])
        title = _clean(home.title)
        if title and not _GENERIC_TITLE.match(title):
            first = _TITLE_SUFFIX.split(title)[0].strip()
            if 1 < len(first) <= 40:
                return first
        if home.headings:
            h = _clean(home.headings[0])
            if 1 < len(h) <= 40:
                return h
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        return host.split(".")[0].capitalize()

    def _tagline(self, home: ScannedPage) -> str:
        if home.og.get("description"):
            s = _sentences(home.og["description"])
            if s:
                return s[0]
        if home.meta_description:
            s = _sentences(home.meta_description)
            if s:
                return s[0]
        for h in home.headings[:3]:
            hc = _clean(h)
            if 10 <= len(hc) <= 120:
                return hc
        return ""

    def _desc_short(self, home: ScannedPage, tagline: str) -> str:
        if home.meta_description:
            return _clean(home.meta_description)[:300]
        if home.og.get("description"):
            return _clean(home.og["description"])[:300]
        return tagline

    def _desc_long(self, pages: list[ScannedPage], short: str) -> str:
        paras: list[str] = []
        for p in pages:
            for para in p.paragraphs:
                pc = _clean(para)
                if len(pc) >= 60 and pc not in paras:
                    paras.append(pc)
                if len(paras) >= 5:
                    break
            if len(paras) >= 5:
                break
        joined = " ".join(paras)
        return (joined or short)[:1200]

    def _categories(self, lower: str) -> list[str]:
        scored: Counter = Counter()
        for cat, kws in _CATEGORY_KEYWORDS.items():
            for kw in kws:
                scored[cat] += lower.count(kw)
        ranked = [c for c, n in scored.most_common() if n > 0]
        return ranked[:4] or ["Software"]

    def _tags(self, lower: str, categories: list[str]) -> list[str]:
        tags = [c.lower().replace(" ", "-") for c in categories]
        extra = ["automation", "open-source", "free", "no-code", "api", "saas", "ai"]
        for e in extra:
            if e.replace("-", " ") in lower and e not in tags:
                tags.append(e)
        return tags[:8]

    def _features(self, pages: list[ScannedPage]) -> list[dict]:
        feats: list[dict] = []
        seen: set[str] = set()
        # 1) explicit list items are the strongest feature signal
        for p in pages:
            for li in p.list_items:
                t = _clean(li)
                key = t.lower()
                if 8 <= len(t) <= 90 and key not in seen and not t.endswith("?"):
                    seen.add(key)
                    feats.append({"title": t, "description": ""})
        # 2) headings under a "features"-ish section
        for p in pages:
            for h in p.headings:
                t = _clean(h)
                key = t.lower()
                if 8 <= len(t) <= 70 and key not in seen and not _FEATURE_HEADING.search(t):
                    seen.add(key)
                    feats.append({"title": t, "description": ""})
        return feats[:8]

    def _benefits(self, pages: list[ScannedPage]) -> list[str]:
        benefits: list[str] = []
        seen: set[str] = set()
        for p in pages:
            for s in _sentences(p.text):
                if _BENEFIT_CUES.search(s) and 15 <= len(s) <= 160:
                    key = s.lower()
                    if key not in seen:
                        seen.add(key)
                        benefits.append(s)
                if len(benefits) >= 6:
                    return benefits
        return benefits

    def _icp(self, lower: str) -> str:
        for pattern, label in _ICP_HINTS:
            if re.search(pattern, lower):
                return label
        return "Software teams and individual makers looking for this solution"

    def _positioning(self, name: str, tagline: str, categories: list[str]) -> str:
        cat = categories[0] if categories else "software"
        if tagline:
            return f"{name} is a {cat} product: {tagline}"
        return f"{name} is a {cat} product."

    def _pricing(self, lower: str) -> str:
        if "free forever" in lower or "100% free" in lower:
            return "Free"
        if re.search(r"\$\d+\s*/\s*(mo|month)", lower) or "pricing" in lower:
            if "free" in lower:
                return "Freemium (free tier + paid plans)"
            return "Paid"
        if "free" in lower:
            return "Free"
        return ""

    def _social_links(self, pages: list[ScannedPage]) -> dict[str, str]:
        social: dict[str, str] = {}
        patterns = {
            "twitter": r"https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+",
            "github": r"https?://(?:www\.)?github\.com/[A-Za-z0-9_\-]+",
            "linkedin": r"https?://(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_\-]+",
        }
        for p in pages:
            for link in p.links:
                for key, pat in patterns.items():
                    if key not in social and re.match(pat, link):
                        social[key] = link
        return social
