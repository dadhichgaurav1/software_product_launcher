"""Service layer used by the API routes.

Kept separate from FastAPI so it can be unit-tested directly and so the analyzer
construction can be overridden in tests (offline fetcher) via the factory hooks.
"""
from __future__ import annotations

import logging

from ..analyzer.product_analyzer import ProductAnalyzer, default_asset_downloader
from ..answers.best_practices import live_researcher
from ..answers.generator import AnswerGenerator
from ..config import settings
from ..llm.factory import get_provider
from ..models import AnswerSet, Product
from ..registry import sites as registry
from ..store.product_store import ProductStore

log = logging.getLogger(__name__)

_store: ProductStore | None = None


def store() -> ProductStore:
    global _store
    if _store is None:
        _store = ProductStore()
    return _store


# -- factory hooks (overridable in tests) -----------------------------------
def get_analyzer() -> ProductAnalyzer:
    return ProductAnalyzer(asset_downloader=default_asset_downloader)


def get_generator() -> AnswerGenerator:
    provider = get_provider()
    # Live best-practice research only makes sense with a real LLM/network.
    researcher = None
    if provider.name == "openai":
        researcher = live_researcher(provider)
    return AnswerGenerator(provider=provider, researcher=researcher)


# -- operations -------------------------------------------------------------
def scan(url: str, force: bool = False) -> Product:
    """Return the stored product, re-analyzing when missing or force-refreshed."""
    st = store()
    if not force:
        existing = st.load(url)
        if existing is not None:
            log.info("Returning cached product for %s (v%s)", url, existing.version)
            return existing
    product = get_analyzer().analyze(url)
    return st.save(product, force=force)


def get_product(url: str) -> Product | None:
    return store().load(url)


def delete_product(url: str) -> bool:
    return store().delete(url)


def list_products() -> list[dict]:
    return store().list_summaries()


def generate(url: str, site_ids: list[str] | None = None, force_scan: bool = False) -> list[AnswerSet]:
    product = scan(url, force=force_scan)
    gen = get_generator()
    targets = _resolve_sites(site_ids)
    return [gen.generate(product, site) for site in targets]


def generate_one(url: str, site_id: str, force_scan: bool = False) -> AnswerSet:
    product = scan(url, force=force_scan)
    site = registry.get_site(site_id)
    if site is None:
        raise KeyError(site_id)
    return get_generator().generate(product, site)


def _resolve_sites(site_ids: list[str] | None):
    if not site_ids:
        return registry.all_sites()
    out = []
    for sid in site_ids:
        site = registry.get_site(sid)
        if site is not None:
            out.append(site)
    return out
