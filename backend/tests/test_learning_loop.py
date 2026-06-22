"""Post-launch learning loop: capture → reason → learn → feed the next launch.

Offline (mock provider). The headline test proves the loop is *closed*: a logged
outcome produces a learning that demonstrably appears in the best_practices fed
into the NEXT generation for that site.
"""
import shutil

import pytest

from app.analyzer.product_analyzer import ProductAnalyzer
from app.api import services
from app.config import settings
from app.ingest import fetch_hn_outcome, utm_url
from app.llm.mock_provider import MockProvider
from app.models import LaunchBook
from app.scanner.crawler import Crawler

from tests.fixtures.fake_site import BASE, fake_fetcher


@pytest.fixture(autouse=True)
def offline_and_isolated(monkeypatch):
    """Offline analyzer + wipe the launches dir (incl. the shared global file)."""
    monkeypatch.setattr(
        services,
        "get_analyzer",
        lambda: ProductAnalyzer(crawler=Crawler(fetcher=fake_fetcher, max_pages=10)),
    )
    ldir = settings.data_dir / "launches"
    if ldir.exists():
        shutil.rmtree(ldir)
    services._launches = None
    yield
    if ldir.exists():
        shutil.rmtree(ldir)
    services._launches = None


def _setup_drafts():
    services.scan(BASE)
    services.generate(BASE, ["devhunt"], regenerate=True)


def test_outcome_produces_and_persists_learnings():
    _setup_drafts()
    services.record_launch(BASE, "devhunt")
    result = services.record_outcome(BASE, "devhunt", status="featured", rank=3, points=150, signups=0)
    assert result["learnings"], "a strong outcome should yield learnings"
    book = services.get_launches(BASE)
    assert book.learnings, "learnings persisted to the product launch book"
    assert book.launches["devhunt"].outcomes[0].points == 150
    assert services.learnings_for_site("devhunt"), "global feed-forward populated"


def test_loop_is_closed_learning_feeds_next_generation(monkeypatch):
    _setup_drafts()
    services.record_launch(BASE, "devhunt")
    services.record_outcome(BASE, "devhunt", status="featured", rank=3, points=150, signups=0)
    learning_texts = services.learnings_for_site("devhunt")
    assert learning_texts

    # Spy on the practices actually passed into generation.
    captured: dict[str, list[str]] = {}
    orig = MockProvider.generate_answer

    def spy(self, *, question, product, site, best_practices):
        captured.setdefault(site.id, []).extend(best_practices)
        return orig(self, question=question, product=product, site=site, best_practices=best_practices)

    monkeypatch.setattr(MockProvider, "generate_answer", spy)

    services.generate(BASE, ["devhunt"], regenerate=True)
    blob = " ".join(captured.get("devhunt", []))
    assert any(text in blob for text in learning_texts), "learning fed forward into the next generation"


def test_delete_keeps_shared_global_learnings():
    _setup_drafts()
    services.record_outcome(BASE, "devhunt", status="featured", points=150)
    assert services.learnings_for_site("devhunt")
    services.delete_product(BASE)
    assert services.get_launches(BASE).launches == {}, "product launch book deleted"
    assert services.learnings_for_site("devhunt"), "shared global learnings survive a single-product delete"


def test_launchbook_roundtrips_nested_models():
    _setup_drafts()
    services.record_launch(BASE, "devhunt")
    services.record_outcome(BASE, "devhunt", status="live", points=42, sentiment="positive")
    book = services.get_launches(BASE)
    again = LaunchBook.model_validate(book.model_dump())  # nested Launch/Outcome/CopySnapshot
    launch = again.launches["devhunt"]
    assert launch.outcomes[0].points == 42 and launch.outcomes[0].sentiment == "positive"
    assert launch.submitted_copy.tagline  # snapshot captured the copy


def test_reflect_is_idempotent_on_global_store():
    _setup_drafts()
    services.record_launch(BASE, "devhunt")
    services.record_outcome(BASE, "devhunt", status="featured", points=150, signups=0)
    n1 = len(services.learnings_for_site("devhunt"))
    # same outcome again → identical learning text → de-duped by id
    services.record_outcome(BASE, "devhunt", status="featured", points=150, signups=0)
    n2 = len(services.learnings_for_site("devhunt"))
    assert n2 == n1, "identical learnings must not accumulate in the global store"


# -- ingestion helpers -------------------------------------------------------
def test_hn_ingest_with_fake_fetcher():
    out = fetch_hn_outcome(
        "TaskPilot",
        fetcher=lambda url: {"hits": [{"points": 87, "num_comments": 21, "title": "Show HN: TaskPilot"}]},
    )
    assert out and out.points == 87 and out.comments == 21 and out.source == "hn"


def test_hn_ingest_handles_no_hits_and_errors():
    assert fetch_hn_outcome("x", fetcher=lambda url: {"hits": []}) is None

    def boom(url):
        raise RuntimeError("network down")

    assert fetch_hn_outcome("x", fetcher=boom) is None  # degrades to None


def test_utm_url_preserves_existing_query():
    u = utm_url("https://taskpilot.ai/?ref=hn", "devhunt")
    assert "utm_source=devhunt" in u
    assert "utm_campaign=launch" in u
    assert "ref=hn" in u
    assert u.startswith("https://taskpilot.ai/")
