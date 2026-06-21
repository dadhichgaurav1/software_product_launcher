"""Asset extraction: logo, favicon, og:image, images and videos.

Works purely on parsed HTML (BeautifulSoup) so it is fully offline-testable.
Downloading is optional and guarded by settings.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..config import settings
from ..models import Asset, ProductAssets

log = logging.getLogger(__name__)

_LOGO_HINT = re.compile(r"logo|brand|wordmark", re.I)
_IMG_EXT = re.compile(r"\.(png|jpe?g|svg|webp|gif|avif)(\?|$)", re.I)


def extract_from_soup(soup: BeautifulSoup, page_url: str) -> list[Asset]:
    """Return raw candidate assets found on one page (not yet deduped/downloaded)."""
    out: list[Asset] = []

    # favicon / apple-touch-icon
    for link in soup.find_all("link", rel=True):
        rel = " ".join(link.get("rel", [])).lower()
        href = link.get("href")
        if not href:
            continue
        if "icon" in rel:
            out.append(Asset(kind="favicon", url=urljoin(page_url, href)))

    # Open Graph / Twitter card image
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        content = meta.get("content")
        if content and prop in {"og:image", "og:image:url", "twitter:image"}:
            out.append(Asset(kind="og_image", url=urljoin(page_url, content)))

    # <img> elements — flag likely logos
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src or src.startswith("data:"):
            continue
        url = urljoin(page_url, src)
        alt = (img.get("alt") or "").strip()
        cls = " ".join(img.get("class") or [])
        ident = f"{alt} {cls} {img.get('id') or ''} {src}"
        kind = "logo" if _LOGO_HINT.search(ident) else "image"
        out.append(
            Asset(
                kind=kind,
                url=url,
                alt=alt or None,
                width=_to_int(img.get("width")),
                height=_to_int(img.get("height")),
            )
        )

    # <video> / <source> and youtube/vimeo embeds
    for video in soup.find_all("video"):
        src = video.get("src")
        if src:
            out.append(Asset(kind="video", url=urljoin(page_url, src)))
        for source in video.find_all("source"):
            if source.get("src"):
                out.append(Asset(kind="video", url=urljoin(page_url, source["src"])))
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or ""
        if re.search(r"youtube\.com|youtu\.be|vimeo\.com|wistia", src, re.I):
            out.append(Asset(kind="video", url=urljoin(page_url, src)))

    return out


def finalize_assets(candidates: list[Asset], *, downloader=None) -> ProductAssets:
    """Dedupe candidates, pick the best logo/favicon, optionally download."""
    seen: set[str] = set()
    unique: list[Asset] = []
    for a in candidates:
        if a.url in seen:
            continue
        seen.add(a.url)
        unique.append(a)

    logo = _pick_logo(unique)
    favicon = next((a for a in unique if a.kind == "favicon"), None)
    images = [a for a in unique if a.kind in {"image", "og_image"} and a is not logo]
    videos = [a for a in unique if a.kind == "video"]

    result = ProductAssets(
        logo=logo,
        favicon=favicon,
        images=images[:20],
        videos=videos[:10],
    )

    if downloader and settings.download_assets:
        for asset in _iter_assets(result):
            try:
                downloader(asset)
            except Exception as exc:  # noqa: BLE001
                log.debug("asset download skipped for %s (%s)", asset.url, exc)

    return result


def _pick_logo(assets: list[Asset]) -> Asset | None:
    logos = [a for a in assets if a.kind == "logo"]
    if logos:
        return logos[0]
    # Fall back to the first OG image as a representative brand image.
    return next((a for a in assets if a.kind == "og_image"), None)


def _iter_assets(pa: ProductAssets):
    if pa.logo:
        yield pa.logo
    if pa.favicon:
        yield pa.favicon
    yield from pa.images
    yield from pa.videos


def _to_int(val) -> int | None:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def same_site(a: str, b: str) -> bool:
    return _host(a) == _host(b)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")
