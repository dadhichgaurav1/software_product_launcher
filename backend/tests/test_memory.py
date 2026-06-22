"""Offline tests for the Synap memory layer.

A fake **async** SDK is injected (no network). They assert: NullMemory is the
default with no key; SynapMemory scopes ingest by user_id=product_key /
customer_id=config; record_message / memories.create are called with the right
args; recall maps the fetch response to a list; and failures degrade silently.
"""
import pytest

from app.config import settings
from app.memory import get_memory, reset_memory
from app.memory.null_memory import NullMemory
from app.models import Product
from app.store.product_store import product_key


# -- fake async Synap SDK ----------------------------------------------------
class _FakeConversation:
    def __init__(self, calls):
        self._calls = calls

    async def record_message(self, **kwargs):
        self._calls.append(("record_message", kwargs))
        return {"ok": True}


class _FakeMemories:
    def __init__(self, calls):
        self._calls = calls

    async def create(self, **kwargs):
        self._calls.append(("memories.create", kwargs))
        return {"id": "mem-1"}


class _FakeResp:
    def format_for_prompt(self):
        return "Prefers concise, benefit-led taglines\n- Always say 'AI teammate'"


class _FakeSDK:
    def __init__(self, **kwargs):
        self.calls = []
        self.init_kwargs = kwargs
        self.conversation = _FakeConversation(self.calls)
        self.memories = _FakeMemories(self.calls)

    async def initialize(self):
        self.calls.append(("initialize", {}))

    async def fetch(self, **kwargs):
        self.calls.append(("fetch", kwargs))
        return _FakeResp()


@pytest.fixture()
def synap(monkeypatch):
    """A SynapMemory wired to the fake SDK, with the cache reset around it."""
    import app.memory.synap_memory as sm

    monkeypatch.setattr(sm, "MaximemSynapSDK", _FakeSDK)
    monkeypatch.setattr(settings, "synap_api_key", "sk-synap-test")
    monkeypatch.setattr(settings, "synap_customer_id", "acme")
    reset_memory()
    mem = get_memory(force="synap")
    yield mem
    reset_memory()


def _product():
    return Product(url="https://taskpilot.ai", name="TaskPilot", tagline="Your AI project manager",
                   positioning="AI PM", icp="Founders", categories=["AI", "Productivity"],
                   benefits=["Save hours every week"])


def test_default_is_null_without_key(monkeypatch):
    monkeypatch.setattr(settings, "synap_api_key", None)
    monkeypatch.setattr(settings, "memory_provider", "auto")
    reset_memory()
    assert isinstance(get_memory(), NullMemory)
    assert get_memory().health()["enabled"] is False
    reset_memory()


def test_synap_initializes_and_is_enabled(synap):
    assert synap.name == "synap"
    assert synap.health()["enabled"] is True
    assert ("initialize", {}) in synap._sdk.calls


def test_remember_product_scopes_correctly(synap):
    p = _product()
    synap.remember_product(p)
    kind, kwargs = next(c for c in synap._sdk.calls if c[0] == "record_message")
    assert kwargs["user_id"] == product_key(p.url)
    assert kwargs["customer_id"] == "acme"
    assert kwargs["conversation_id"] == f"launch:{product_key(p.url)}"
    assert "TaskPilot" in kwargs["content"]


def test_remember_edit_and_instruction(synap):
    p = _product()
    synap.remember_edit(p.url, "devhunt", "Tagline", "🤖 Ship faster")
    synap.remember_instruction(p.url, "always lead with the benefit", "all drafts", "Updated 3 fields")
    records = [c for c in synap._sdk.calls if c[0] == "record_message"]
    assert any("Tagline" in c[1]["content"] and c[1]["metadata"]["site_id"] == "devhunt" for c in records)
    assert any("lead with the benefit" in c[1]["content"] for c in records)


def test_remember_outcome_and_learnings_use_memories_create(synap):
    p = _product()
    synap.remember_outcome(p.url, "devhunt", "#3 of the day, 120 upvotes", {"points": 120})
    synap.remember_learnings(p.url, "devhunt", ["Benefit-led taglines win on DevHunt"])
    creates = [c for c in synap._sdk.calls if c[0] == "memories.create"]
    assert len(creates) == 2
    for _, kwargs in creates:
        # M3: first arg is a string `document`, not a CreateMemoryRequest
        assert isinstance(kwargs["document"], str)
        assert kwargs["user_id"] == product_key(p.url)
        assert kwargs["customer_id"] == "acme"


def test_recall_maps_response_to_lines(synap):
    p = _product()
    lines = synap.recall(p.url, query="tagline", site_id="devhunt")
    assert "Prefers concise, benefit-led taglines" in lines
    assert any("AI teammate" in ln for ln in lines)
    # fetch was scoped
    _, kwargs = next(c for c in synap._sdk.calls if c[0] == "fetch")
    assert kwargs["user_id"] == product_key(p.url) and kwargs["customer_id"] == "acme"
    assert kwargs["search_query"] == ["tagline"]


def test_recall_degrades_to_empty_on_error(synap, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("synap down")

    monkeypatch.setattr(synap._sdk, "fetch", boom)
    assert synap.recall(_product().url, query="x") == []


def test_ingest_swallows_errors(synap, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("synap down")

    monkeypatch.setattr(synap._sdk.conversation, "record_message", boom)
    # must not raise
    synap.remember_product(_product())
