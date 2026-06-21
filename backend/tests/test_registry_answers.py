"""Tests for the launch-site registry and the answer generator."""
import pytest

from app.analyzer.product_analyzer import ProductAnalyzer
from app.answers.generator import AnswerGenerator
from app.registry import sites
from app.scanner.crawler import Crawler

from tests.fixtures.fake_site import BASE, fake_fetcher

# All 20 launch sites from the requirements must be present.
EXPECTED_IDS = {
    "launchpadindia", "betalist", "uneed", "peerlist", "fazier", "devhunt",
    "showhn", "microlaunch", "smollaunch", "tinystartups", "tinylaunch",
    "startupbase", "indiehackers", "launchingnext", "openhunts", "firsto",
    "pitchwall", "launchigniter", "saashub", "alternativeto",
}


@pytest.fixture(scope="module")
def product():
    analyzer = ProductAnalyzer(crawler=Crawler(fetcher=fake_fetcher, max_pages=10))
    return analyzer.analyze(BASE)


def test_all_20_sites_present_and_valid():
    ids = set(sites.site_ids())
    assert ids == EXPECTED_IDS, f"missing: {EXPECTED_IDS - ids}, extra: {ids - EXPECTED_IDS}"
    assert sites.validate_registry() == []


def test_every_site_has_core_fields_and_questions():
    for site in sites.all_sites():
        assert site.name and site.url
        assert site.questions, f"{site.id} has no questions"
        assert site.best_practices, f"{site.id} has no best practices"
        # core mappings that the product can fill
        maps = {q.maps_to for q in site.questions}
        assert "url" in maps or any(q.type == "url" for q in site.questions), site.id


def test_generate_answers_for_every_site(product):
    gen = AnswerGenerator()
    for site in sites.all_sites():
        aset = gen.generate(product, site)
        assert aset.site_id == site.id
        assert len(aset.answers) == len(site.questions)
        # at least the name/url-style fields should be populated for any product
        filled = [a for a in aset.answers if a.value]
        assert filled, f"{site.id}: no answers were filled"
        # fill plan steps reference real selectors
        for step in aset.fill_plan:
            assert step.selectors, f"{site.id}: fill step missing selectors"
            assert step.action in {"fill", "select", "check", "upload", "click"}


def test_max_length_respected(product):
    gen = AnswerGenerator()
    for site in sites.all_sites():
        aset = gen.generate(product, site)
        by_id = {q.id: q for q in site.questions}
        for ans in aset.answers:
            q = by_id[ans.question_id]
            if q.max_length and ans.value:
                assert len(ans.value) <= q.max_length, f"{site.id}.{q.id} exceeds max_length"


def test_betalist_maps_product_fields(product):
    site = sites.get_site("betalist")
    aset = AnswerGenerator().generate(product, site)
    answers = {a.question_id: a.value for a in aset.answers}
    assert answers["name"] == product.name
    assert answers["url"].startswith("http")
    assert answers["pitch"], "pitch should map from tagline"
