"""Product analyzer: orchestrates scan → LLM understanding → assets → Product.

This is the bridge between the raw crawl and the canonical, well-structured
product JSON persisted on the server.
"""
from __future__ import annotations

import logging
import re

from ..config import settings
from ..llm.base import LLMProvider
from ..llm.factory import get_provider
from ..models import Asset, Feature, Product, ProductAssets
from ..scanner import assets as assets_mod
from ..scanner.crawler import Crawler

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


class ProductAnalyzer:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        crawler: Crawler | None = None,
        asset_downloader=None,
    ) -> None:
        self.provider = provider or get_provider()
        self.crawler = crawler or Crawler()
        self.asset_downloader = asset_downloader

    def analyze(self, url: str) -> Product:
        crawl = self.crawler.crawl(url)
        if not crawl.pages:
            raise ValueError(f"Could not fetch any pages from {url}")

        fields = self.provider.analyze_product(url, crawl.pages)
        assets = assets_mod.finalize_assets(
            crawl.asset_candidates, downloader=self.asset_downloader
        )
        product = self._build(url, crawl.canonical_url, fields, assets, crawl.pages)
        product.maker_email = product.maker_email or self._find_email(crawl.pages)
        log.info("Analyzed %s as '%s' via %s", url, product.name, self.provider.name)
        return product

    # ------------------------------------------------------------------
    def _build(self, url, canonical, fields, assets, pages) -> Product:
        features = [
            Feature(**f) if isinstance(f, dict) else Feature(title=str(f))
            for f in (fields.get("features") or [])
        ]
        return Product(
            url=url.rstrip("/"),
            canonical_url=canonical or url,
            analyzed_by=self.provider.name,
            name=_s(fields.get("name")),
            tagline=_s(fields.get("tagline")),
            description_short=_s(fields.get("description_short")),
            description_long=_s(fields.get("description_long")),
            positioning=_s(fields.get("positioning")),
            icp=_s(fields.get("icp")),
            target_group=_s(fields.get("target_group")),
            categories=_list(fields.get("categories")),
            topics_tags=_list(fields.get("topics_tags")),
            features=features,
            benefits=_list(fields.get("benefits")),
            pricing=_s(fields.get("pricing")),
            social_links=fields.get("social_links") or {},
            maker_name=_s(fields.get("maker_name")),
            maker_email=_s(fields.get("maker_email")),
            assets=assets if isinstance(assets, ProductAssets) else ProductAssets(),
            pages_scanned=[p.url for p in pages],
            raw_pages=pages,
        )

    @staticmethod
    def _find_email(pages) -> str:
        for p in pages:
            m = _EMAIL_RE.search(p.text)
            if m and not m.group(0).endswith((".png", ".jpg")):
                return m.group(0)
        return ""


def default_asset_downloader(asset: Asset) -> None:
    """Download an asset into the assets dir and set its local_path (best effort)."""
    if not settings.download_assets:
        return
    import httpx

    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": settings.crawl_user_agent}
    with httpx.Client(follow_redirects=True, timeout=settings.crawl_timeout_s, headers=headers) as c:
        resp = c.get(asset.url)
        if resp.status_code >= 400:
            return
        if len(resp.content) > settings.max_asset_bytes:
            return
        name = re.sub(r"[^a-zA-Z0-9.\-]+", "_", asset.url.split("/")[-1].split("?")[0]) or "asset"
        path = settings.assets_dir / name
        path.write_bytes(resp.content)
        asset.local_path = str(path)
        asset.mime = resp.headers.get("content-type")


def _s(val) -> str:
    return (val or "").strip() if isinstance(val, str) else (str(val) if val else "")


def _list(val) -> list:
    if isinstance(val, list):
        return [v for v in val if v]
    if isinstance(val, str) and val:
        return [v.strip() for v in val.split(",") if v.strip()]
    return []
