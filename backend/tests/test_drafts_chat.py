"""Tests for draft persistence, inline editing, and agent-chat revision."""
import pytest
from fastapi.testclient import TestClient

from app.analyzer.product_analyzer import ProductAnalyzer
from app.api import services
from app.main import app
from app.scanner.crawler import Crawler

from tests.fixtures.fake_site import BASE, fake_fetcher


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        services, "get_analyzer",
        lambda: ProductAnalyzer(crawler=Crawler(fetcher=fake_fetcher, max_pages=10)),
    )
    yield


@pytest.fixture()
def client():
    c = TestClient(app)
    c.post("/api/generate", json={"url": BASE, "site_ids": ["betalist", "devhunt"]})
    return c


def test_generate_persists_drafts(client):
    r = client.get("/api/drafts", params={"url": BASE})
    assert r.status_code == 200
    bundle = r.json()
    assert "betalist" in bundle["answer_sets"]
    assert bundle["answer_sets"]["betalist"]["answers"]


def test_inline_edit_updates_value_and_fill_step(client):
    r = client.patch("/api/draft/answer", json={
        "url": BASE, "site_id": "betalist", "question_id": "pitch",
        "value": "A hand-written pitch for review",
    })
    assert r.status_code == 200
    aset = r.json()
    pitch = next(a for a in aset["answers"] if a["question_id"] == "pitch")
    assert pitch["value"] == "A hand-written pitch for review"
    assert pitch["edited"] is True
    assert pitch["source"] == "edited"
    step = next(s for s in aset["fill_plan"] if s["question_id"] == "pitch")
    assert step["value"] == "A hand-written pitch for review"


def test_edit_persists_and_answers_endpoint_returns_it(client):
    client.patch("/api/draft/answer", json={
        "url": BASE, "site_id": "devhunt", "question_id": "tagline",
        "value": "Edited tagline stays",
    })
    # the extension endpoint must serve the edited draft, not a fresh generation
    r = client.get("/api/answers/devhunt", params={"url": BASE})
    tagline = next(a for a in r.json()["answers"] if a["question_id"] == "tagline")
    assert tagline["value"] == "Edited tagline stays"


def test_regenerate_false_keeps_edits(client):
    client.patch("/api/draft/answer", json={
        "url": BASE, "site_id": "betalist", "question_id": "pitch", "value": "KEEP ME",
    })
    r = client.post("/api/generate", json={"url": BASE, "site_ids": ["betalist"], "regenerate": False})
    bl = next(s for s in r.json()["answer_sets"] if s["site_id"] == "betalist")
    assert next(a for a in bl["answers"] if a["question_id"] == "pitch")["value"] == "KEEP ME"
    # regenerate=True overwrites
    r2 = client.post("/api/generate", json={"url": BASE, "site_ids": ["betalist"], "regenerate": True})
    bl2 = next(s for s in r2.json()["answer_sets"] if s["site_id"] == "betalist")
    assert next(a for a in bl2["answers"] if a["question_id"] == "pitch")["value"] != "KEEP ME"


def test_chat_add_emoji_then_formalize(client):
    r = client.post("/api/chat", json={
        "url": BASE, "site_ids": ["betalist"], "instruction": "add an emoji to make it fun",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["changed_fields"] > 0
    assert "betalist" in body["updated_site_ids"]
    bl = next(s for s in body["answer_sets"] if s["site_id"] == "betalist")
    pitch = next(a for a in bl["answers"] if a["question_id"] == "pitch")
    assert any(ord(c) >= 0x2600 for c in pitch["value"]), "expected an emoji in the pitch"

    # chat history persisted (user + assistant)
    hist = client.get("/api/chat/history", params={"url": BASE}).json()["chat"]
    assert hist[-2]["role"] == "user" and hist[-1]["role"] == "assistant"

    # now formalize → emoji removed
    r2 = client.post("/api/chat", json={
        "url": BASE, "site_ids": ["betalist"], "instruction": "make it more professional, no emoji",
    })
    bl2 = next(s for s in r2.json()["answer_sets"] if s["site_id"] == "betalist")
    pitch2 = next(a for a in bl2["answers"] if a["question_id"] == "pitch")
    assert not any(ord(c) >= 0x2600 for c in pitch2["value"])


def test_chat_field_focus_only_touches_targeted_field(client):
    before = client.get("/api/drafts", params={"url": BASE}).json()["answer_sets"]["betalist"]
    name_before = next(a for a in before["answers"] if a["question_id"] == "name")["value"]
    r = client.post("/api/chat", json={
        "url": BASE, "site_ids": ["betalist"], "instruction": "shorten the description please",
    })
    bl = next(s for s in r.json()["answer_sets"] if s["site_id"] == "betalist")
    name_after = next(a for a in bl["answers"] if a["question_id"] == "name")["value"]
    assert name_after == name_before, "name should be untouched when focusing on description"


def test_chat_requires_drafts(client):
    r = client.post("/api/chat", json={"url": "https://never-scanned.example", "instruction": "shorten"})
    assert r.status_code == 404
