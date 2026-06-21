"""Website crawler.

Fetches a product site, follows same-domain links (prioritising informative
pages like /features, /pricing, /about) up to a configured page budget, and
returns structured ScannedPage objects plus candidate assets.

The HTTP fetcher is injectable so the crawler is fully offline-testable: pass a
``fetcher`` that returns FetchResult objects from local fixtures.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from ..config import settings
from ..models import Asset, ScannedPage
from . import assets as assets_mod

log = logging.getLogger(__name__)

# Paths worth prioritising when choosing which links to follow.
_PRIORITY = re.compile(
    r"/(features?|product|pricing|about|how-it-works|use-cases?|solutions?|"
    r"why|tour|overview|home)\b",
    re.I,
)
_SKIP = re.compile(
    r"/(blog|docs?|terms|privacy|legal|careers?|jobs|login|signin|signup|"
    r"register|cart|checkout|account|api-reference)\b|\.(pdf|zip|dmg|exe)$",
    re.I,
)
_DROP_TAGS = ("script", "style", "noscript", "template", "svg")


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    status: int
    html: str
    content_type: str = "text/html"


@dataclass
class CrawlResult:
    pages: list[ScannedPage]
    asset_candidates: list[Asset] = field(default_factory=list)
    canonical_url: str = ""


def httpx_fetcher(url: str) -> FetchResult:
    """Default network fetcher using httpx (used when not running offline tests)."""
    import httpx

    headers = {"User-Agent": settings.crawl_user_agent}
    with httpx.Client(
        follow_redirects=True, timeout=settings.crawl_timeout_s, headers=headers
    ) as client:
        resp = client.get(url)
        return FetchResult(
            url=str(resp.url),
            status=resp.status_code,
            html=resp.text,
            content_type=resp.headers.get("content-type", "text/html"),
        )


class Crawler:
    def __init__(self, fetcher=None, max_pages: int | None = None) -> None:
        self.fetcher = fetcher or httpx_fetcher
        self.max_pages = max_pages or settings.crawl_max_pages

    def crawl(self, start_url: str) -> CrawlResult:
        start_url = _normalize(start_url)
        queue: list[str] = [start_url]
        visited: set[str] = set()
        pages: list[ScannedPage] = []
        candidates: list[Asset] = []
        canonical = start_url

        while queue and len(pages) < self.max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                res = self.fetcher(url)
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch failed for %s (%s)", url, exc)
                continue
            if res.status >= 400 or "html" not in res.content_type:
                continue

            soup = BeautifulSoup(res.html, "lxml")
            page = self._parse_page(soup, res.url)
            pages.append(page)
            candidates.extend(assets_mod.extract_from_soup(soup, res.url))

            if len(pages) == 1:
                canonical = self._canonical(soup, res.url)

            # enqueue same-site links, priority pages first
            new_links = self._select_links(page.links, start_url, visited, set(queue))
            queue.extend(new_links)

        return CrawlResult(pages=pages, asset_candidates=candidates, canonical_url=canonical)

    # ------------------------------------------------------------------
    def _parse_page(self, soup: BeautifulSoup, url: str) -> ScannedPage:
        title = (soup.title.string if soup.title and soup.title.string else "").strip()

        meta_desc = ""
        og: dict[str, str] = {}
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            content = (meta.get("content") or "").strip()
            if not content:
                continue
            if prop in {"description"}:
                meta_desc = content
            if prop.startswith("og:"):
                og[prop[3:]] = content
            elif prop == "twitter:description" and "description" not in og:
                og["description"] = content

        headings = [
            h.get_text(" ", strip=True)
            for h in soup.find_all(["h1", "h2", "h3"])
            if h.get_text(strip=True)
        ][:40]
        list_items = [
            li.get_text(" ", strip=True)
            for li in soup.find_all("li")
            if li.get_text(strip=True)
        ][:60]
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 30
        ][:40]

        for tag in soup(_DROP_TAGS):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:20000]

        links = []
        for a in soup.find_all("a", href=True):
            href = urldefrag(urljoin(url, a["href"]))[0]
            if href.startswith("http"):
                links.append(href)

        return ScannedPage(
            url=url,
            title=title,
            meta_description=meta_desc,
            og=og,
            headings=headings,
            list_items=list_items,
            paragraphs=paragraphs,
            text=text,
            links=_dedupe(links),
        )

    def _select_links(self, links, start_url, visited, queued) -> list[str]:
        out: list[str] = []
        seen = visited | queued
        prioritized, normal = [], []
        for link in links:
            link = _normalize(link)
            if link in seen or link in out:
                continue
            if not assets_mod.same_site(link, start_url):
                continue
            if _SKIP.search(urlparse(link).path):
                continue
            (prioritized if _PRIORITY.search(urlparse(link).path) else normal).append(link)
        out.extend(prioritized)
        out.extend(normal)
        return out

    @staticmethod
    def _canonical(soup: BeautifulSoup, url: str) -> str:
        link = soup.find("link", rel=lambda v: v and "canonical" in v)
        if link and link.get("href"):
            return urljoin(url, link["href"])
        return url


def _normalize(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = urldefrag(url)[0]
    return url.rstrip("/") if urlparse(url).path in ("", "/") else url


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
