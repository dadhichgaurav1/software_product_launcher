"""Offline tests for OpenAI per-task model routing + Structured Outputs.

These never touch the network: the OpenAI client is replaced with a fake that
records calls and returns canned responses. They assert the routing, the
structured-output → JSON-mode → mock fallback chain, the M1 strict-schema fix,
and the service_tier guard (empty string must be omitted).
"""
import json

import pytest

from app.config import settings
from app.llm.openai_provider import (
    OpenAIProvider,
    ProductUnderstanding,
    _understanding_to_dict,
)
from app.models import LaunchSite, Product, Question, ScannedPage


# -- fake OpenAI client ------------------------------------------------------
class _Msg:
    def __init__(self, content=None, parsed=None, refusal=None):
        self.content = content
        self.parsed = parsed
        self.refusal = refusal


class _Completion:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]


class _FakeCompletions:
    def __init__(self):
        self.calls = []  # (kind, kwargs)
        self.parse_raises = False
        self.parsed_obj = None
        self.text = "Generated text"

    def parse(self, **kwargs):
        self.calls.append(("parse", kwargs))
        if self.parse_raises:
            raise RuntimeError("parse unavailable")
        return _Completion(_Msg(parsed=self.parsed_obj))

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        rf = kwargs.get("response_format")
        if isinstance(rf, dict) and rf.get("type") == "json_object":
            return _Completion(_Msg(content=json.dumps({"name": "FromJSONMode"})))
        return _Completion(_Msg(content=self.text))


class _FakeClient:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


@pytest.fixture()
def provider(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    # default-clean cost-control config for deterministic assertions
    monkeypatch.setattr(settings, "llm_service_tier", "")
    monkeypatch.setattr(settings, "llm_prompt_cache_key", "")
    monkeypatch.setattr(settings, "llm_structured_outputs", True)
    p = OpenAIProvider()
    fc = _FakeCompletions()
    p.client = _FakeClient(fc)
    return p, fc


def _product():
    return Product(url="https://x.ai", name="X", tagline="Do more", categories=["AI"])


def _site():
    return LaunchSite(id="s", name="Site", url="https://site.com")


def _q(max_length=None):
    return Question(id="tagline", label="Tagline", type="text", max_length=max_length)


# -- M1: strict schema must be valid (no open-ended Dict) --------------------
def test_product_understanding_is_strict_safe():
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(ProductUnderstanding)  # must not raise
    assert schema["properties"]["social_links"]["type"] == "array"
    # strict mode requires every property to be required
    assert set(schema.get("required", [])) == set(schema["properties"].keys())


def test_understanding_to_dict_maps_social_links_list_to_dict():
    u = ProductUnderstanding(
        name="X",
        social_links=[{"platform": "Twitter", "url": "https://x.com/x"}],
    )
    d = _understanding_to_dict(u)
    assert d["social_links"] == {"twitter": "https://x.com/x"}


# -- routing -----------------------------------------------------------------
def test_analyze_uses_analyze_model_and_structured_parse(provider, monkeypatch):
    p, fc = provider
    monkeypatch.setattr(settings, "llm_model_analyze", "analyze-model")
    fc.parsed_obj = ProductUnderstanding(name="Parsed", tagline="T")
    pages = [ScannedPage(url="https://x.ai", title="X")]
    out = p.analyze_product("https://x.ai", pages)
    assert out["name"] == "Parsed"
    kind, kwargs = fc.calls[0]
    assert kind == "parse" and kwargs["model"] == "analyze-model"


def test_generate_uses_generate_model(provider, monkeypatch):
    p, fc = provider
    monkeypatch.setattr(settings, "llm_model_generate", "gen-model")
    fc.text = "A crisp tagline"
    val = p.generate_answer(question=_q(), product=_product(), site=_site(), best_practices=[])
    assert val == "A crisp tagline"
    assert any(k == "create" and kw["model"] == "gen-model" for k, kw in fc.calls)


def test_revise_uses_revise_model(provider, monkeypatch):
    p, fc = provider
    monkeypatch.setattr(settings, "llm_model_revise", "rev-model")
    fc.text = "Shorter."
    val = p.revise_answer(
        question=_q(), product=_product(), site=_site(),
        current_value="Long original value", instruction="shorten", best_practices=[],
    )
    assert val == "Shorter."
    assert any(k == "create" and kw["model"] == "rev-model" for k, kw in fc.calls)


# -- fallback chain ----------------------------------------------------------
def test_analyze_falls_back_to_json_mode_when_parse_raises(provider):
    p, fc = provider
    fc.parse_raises = True
    out = p.analyze_product("https://x.ai", [ScannedPage(url="https://x.ai", title="X")])
    assert out["name"] == "FromJSONMode"
    assert ("parse" in [k for k, _ in fc.calls]) and ("create" in [k for k, _ in fc.calls])
    # the create call used JSON mode
    create = next(kw for k, kw in fc.calls if k == "create")
    assert create["response_format"] == {"type": "json_object"}


def test_generate_fits_to_max_length(provider):
    p, fc = provider
    fc.text = "This tagline is definitely far too long to fit the tiny limit here"
    val = p.generate_answer(question=_q(max_length=20), product=_product(), site=_site(), best_practices=[])
    assert len(val) <= 20


# -- service_tier / prompt_cache_key guard (S4) ------------------------------
def test_service_tier_omitted_when_empty(provider):
    p, fc = provider
    p.generate_answer(question=_q(), product=_product(), site=_site(), best_practices=[])
    _, kwargs = next((k, kw) for k, kw in fc.calls if k == "create")
    assert "service_tier" not in kwargs
    assert "prompt_cache_key" not in kwargs


def test_service_tier_included_when_set(provider, monkeypatch):
    p, fc = provider
    monkeypatch.setattr(settings, "llm_service_tier", "flex")
    monkeypatch.setattr(settings, "llm_prompt_cache_key", "spl-prod")
    p.generate_answer(question=_q(), product=_product(), site=_site(), best_practices=[])
    _, kwargs = next((k, kw) for k, kw in fc.calls if k == "create")
    assert kwargs["service_tier"] == "flex"
    assert kwargs["prompt_cache_key"] == "spl-prod"


class _Copy:
    tagline = "🤖 Save hours with AI"


class _Out:
    site_id = "s"
    points = 120
    rank = 3
    signups = 0
    status = "submitted"


def test_extract_learnings_mock_is_deterministic():
    from app.llm.mock_provider import MockProvider

    learnings = MockProvider().extract_learnings(
        product=_product(), site=_site(), copy=_Copy(), outcomes=[_Out()]
    )
    assert learnings and all(isinstance(s, str) for s in learnings)
    joined = " ".join(learnings).lower()
    assert "performed well" in joined or "benefit" in joined
    assert "signups" in joined or "cta" in joined


def test_openai_extract_learnings_degrades_to_mock(provider):
    # parse + create both raise → OpenAI extract_learnings degrades to the mock.
    p, fc = provider

    def boom(**kwargs):
        raise RuntimeError("down")

    fc.parse = boom  # type: ignore[assignment]
    fc.create = boom  # type: ignore[assignment]
    out = p.extract_learnings(product=_product(), site=_site(), copy=_Copy(), outcomes=[_Out()])
    assert out and all(isinstance(s, str) for s in out)
