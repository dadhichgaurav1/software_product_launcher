"""Tests for the product analyzer orchestration and the JSON store."""
from app.analyzer.product_analyzer import ProductAnalyzer
from app.scanner.crawler import Crawler
from app.store.product_store import ProductStore, product_key

from tests.fixtures.fake_site import BASE, fake_fetcher


def make_product():
    analyzer = ProductAnalyzer(crawler=Crawler(fetcher=fake_fetcher, max_pages=10))
    return analyzer.analyze(BASE)


def test_analyze_builds_full_product():
    p = make_product()
    assert p.name == "TaskPilot"
    assert "task manager" in p.tagline.lower()
    assert p.categories, "categories should be inferred"
    assert p.features, "features should be extracted"
    assert p.assets.logo is not None
    assert p.analyzed_by == "mock"
    assert p.pages_scanned and len(p.pages_scanned) >= 2
    assert "free" in p.pricing.lower()


def test_product_key_is_normalized():
    a = product_key("https://www.Foo.com/")
    b = product_key("http://foo.com")
    assert a == b


def test_store_save_load_force_refresh(tmp_path):
    store = ProductStore(directory=tmp_path)
    p = make_product()
    assert not store.exists(p.url)
    store.save(p)
    assert store.exists(p.url)

    loaded = store.load(p.url)
    assert loaded is not None
    assert loaded.name == "TaskPilot"
    assert loaded.version == 1

    # Re-save without force keeps version; with force bumps it.
    store.save(loaded)
    assert store.load(p.url).version == 1
    store.save(loaded, force=True)
    assert store.load(p.url).version == 2

    summaries = store.list_summaries()
    assert len(summaries) == 1
    assert summaries[0]["name"] == "TaskPilot"

    assert store.delete(p.url) is True
    assert not store.exists(p.url)
