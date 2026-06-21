"""Tests for the crawler + asset extractor (fully offline)."""
from app.scanner import assets as assets_mod
from app.scanner.crawler import Crawler

from tests.fixtures.fake_site import BASE, fake_fetcher


def test_crawler_visits_multiple_pages():
    result = Crawler(fetcher=fake_fetcher, max_pages=10).crawl(BASE)
    urls = {p.url for p in result.pages}
    assert BASE in urls
    assert BASE + "/features" in urls
    assert BASE + "/pricing" in urls
    assert result.canonical_url.startswith(BASE)


def test_crawler_extracts_structure():
    result = Crawler(fetcher=fake_fetcher, max_pages=10).crawl(BASE)
    home = next(p for p in result.pages if p.url.rstrip("/") == BASE)
    assert "AI task manager" in home.title
    assert "AI task manager" in home.meta_description
    assert home.og.get("site_name") == "TaskPilot"
    assert any("sprint" in li.lower() for li in home.list_items)
    assert any("twitter.com/taskpilot" in link for link in home.links)


def test_asset_extraction_finds_logo_favicon_video():
    result = Crawler(fetcher=fake_fetcher, max_pages=10).crawl(BASE)
    assets = assets_mod.finalize_assets(result.asset_candidates)
    assert assets.logo is not None
    assert "logo.svg" in assets.logo.url
    assert assets.favicon is not None and "favicon" in assets.favicon.url
    assert any("demo.mp4" in v.url for v in assets.videos)
    assert any("og.png" in i.url or "screenshot" in i.url for i in assets.images)
