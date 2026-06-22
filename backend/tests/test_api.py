"""End-to-end API tests via FastAPI TestClient (offline)."""
import pytest
from fastapi.testclient import TestClient

from app.analyzer.product_analyzer import ProductAnalyzer
from app.api import services
from app.main import app
from app.scanner.crawler import Crawler

from tests.fixtures.fake_site import BASE, fake_fetcher


@pytest.fixture(autouse=True)
def offline_analyzer(monkeypatch):
    """Force the API's analyzer to use the offline fixture fetcher."""
    monkeypatch.setattr(
        services,
        "get_analyzer",
        lambda: ProductAnalyzer(crawler=Crawler(fetcher=fake_fetcher, max_pages=10)),
    )
    # Fresh store per test run is fine (temp DATA_DIR from conftest).
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sites"] == 20


def test_list_sites(client):
    r = client.get("/api/sites")
    assert r.status_code == 200
    assert r.json()["count"] == 20
    sites = r.json()["sites"]
    ids = {s["id"] for s in sites}
    assert "betalist" in ids and "showhn" in ids
    # the web page needs submit_url to know where to open each site for filling
    assert all(s.get("submit_url") for s in sites)


def test_scan_then_cached_then_force(client):
    r = client.post("/api/scan", json={"url": BASE})
    assert r.status_code == 200
    product = r.json()
    assert product["name"] == "TaskPilot"
    assert product["version"] == 1
    assert "raw_pages" not in product  # public view

    # cached → still version 1
    r2 = client.post("/api/scan", json={"url": BASE})
    assert r2.json()["version"] == 1

    # force → version bumps
    r3 = client.post("/api/scan", json={"url": BASE, "force": True})
    assert r3.json()["version"] == 2


def test_product_listing_and_fetch(client):
    client.post("/api/scan", json={"url": BASE})
    r = client.get("/api/products")
    assert any(p["url"].startswith("https://taskpilot") for p in r.json()["products"])

    r2 = client.get("/api/product", params={"url": BASE})
    assert r2.status_code == 200
    assert r2.json()["name"] == "TaskPilot"


def test_generate_selected_sites(client):
    client.post("/api/scan", json={"url": BASE})
    r = client.post("/api/generate", json={"url": BASE, "site_ids": ["betalist", "devhunt"]})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    sites = {s["site_id"] for s in body["answer_sets"]}
    assert sites == {"betalist", "devhunt"}
    bl = next(s for s in body["answer_sets"] if s["site_id"] == "betalist")
    assert bl["fill_plan"], "betalist should have a fill plan"
    assert any(a["value"] for a in bl["answers"])


def test_answers_endpoint_for_extension(client):
    r = client.get("/api/answers/devhunt", params={"url": BASE})
    assert r.status_code == 200
    aset = r.json()
    assert aset["site_id"] == "devhunt"
    assert aset["fill_plan"]
    assert aset["auth"]["type"] == "github"


def test_generate_all_sites(client):
    r = client.post("/api/generate", json={"url": BASE})
    assert r.status_code == 200
    assert r.json()["count"] == 20


def test_unknown_site_404(client):
    r = client.get("/api/answers/nope", params={"url": BASE})
    assert r.status_code == 404


def test_delete_product(client):
    client.post("/api/scan", json={"url": BASE})
    r = client.delete("/api/product", params={"url": BASE})
    assert r.status_code == 200
    assert client.get("/api/product", params={"url": BASE}).status_code == 404
