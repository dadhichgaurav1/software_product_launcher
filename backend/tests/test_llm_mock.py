"""Tests for the deterministic Mock LLM provider and core models."""
from app.llm.mock_provider import MockProvider
from app.models import LaunchSite, Product, Question, ScannedPage


def sample_pages() -> list[ScannedPage]:
    return [
        ScannedPage(
            url="https://acme.dev",
            title="Acme — AI code review for developers",
            meta_description="Acme is an AI code review tool that saves developers time by "
            "catching bugs automatically. Built for engineering teams.",
            og={"site_name": "Acme", "description": "AI code review for developers."},
            headings=["AI code review for developers", "Features", "Automated bug detection"],
            list_items=[
                "Automated bug detection on every pull request",
                "Inline AI suggestions for developers",
                "Works with GitHub and GitLab APIs",
            ],
            paragraphs=[
                "Acme reviews your pull requests using AI so your team ships faster and "
                "with fewer bugs. Save time on manual code review.",
                "Built for engineering teams that care about quality and speed.",
            ],
            text="Acme is an AI code review tool for developers. It saves time, automates "
            "bug detection and integrates with the GitHub API. Free for open source.",
            links=["https://twitter.com/acme", "https://github.com/acme"],
        )
    ]


def test_analyze_extracts_core_fields():
    data = MockProvider().analyze_product("https://acme.dev", sample_pages())
    assert data["name"] == "Acme"
    assert "code review" in data["tagline"].lower()
    assert "AI" in data["categories"]
    assert "Developer Tools" in data["categories"]
    assert any("bug" in f["title"].lower() for f in data["features"])
    assert data["benefits"], "should detect benefit sentences"
    assert "developer" in data["icp"].lower() or "engineering" in data["icp"].lower()
    assert data["social_links"].get("github") == "https://github.com/acme"
    assert data["social_links"].get("twitter") == "https://twitter.com/acme"


def test_generate_answer_returns_natural_value():
    # The mock returns the natural value; length fitting happens in the generator.
    data = MockProvider().analyze_product("https://acme.dev", sample_pages())
    product = Product(url="https://acme.dev", canonical_url="https://acme.dev", **{
        k: v for k, v in data.items() if k != "features"
    })
    product.features = [{"title": f["title"]} for f in data["features"]]  # type: ignore[assignment]
    site = LaunchSite(id="demo", name="Demo", url="https://demo.test")
    q = Question(id="tagline", label="Tagline", type="text", maps_to="tagline", max_length=20)
    ans = MockProvider().generate_answer(
        question=q, product=product, site=site, best_practices=["Be concise"]
    )
    assert ans, "tagline answer should be non-empty"
    assert ans == product.tagline


def test_url_field_fallback():
    product = Product(url="https://acme.dev", canonical_url="https://acme.dev")
    site = LaunchSite(id="demo", name="Demo", url="https://demo.test")
    q = Question(id="website", label="Website", type="url", maps_to="url")
    ans = MockProvider().generate_answer(
        question=q, product=product, site=site, best_practices=[]
    )
    assert ans == "https://acme.dev"
