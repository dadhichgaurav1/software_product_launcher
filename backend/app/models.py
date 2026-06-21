"""Pydantic data models shared across the backend.

These define the well-structured product JSON stored on the server, the launch
site registry schema, and the generated answer/fill-plan schema consumed by the
Chrome extension.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
class Asset(BaseModel):
    """A media asset discovered on the product site."""

    kind: str  # "logo" | "favicon" | "image" | "video" | "og_image"
    url: str
    local_path: Optional[str] = None
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime: Optional[str] = None


class ScannedPage(BaseModel):
    """Structured content extracted from a single crawled page."""

    url: str
    title: str = ""
    meta_description: str = ""
    og: dict[str, str] = Field(default_factory=dict)
    headings: list[str] = Field(default_factory=list)
    list_items: list[str] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    text: str = ""
    links: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Product understanding (the well-structured JSON persisted on the server)
# ---------------------------------------------------------------------------
class Feature(BaseModel):
    title: str
    description: str = ""


class ProductAssets(BaseModel):
    logo: Optional[Asset] = None
    favicon: Optional[Asset] = None
    images: list[Asset] = Field(default_factory=list)
    videos: list[Asset] = Field(default_factory=list)


class Product(BaseModel):
    """The canonical product understanding stored per URL."""

    url: str
    canonical_url: str = ""
    fetched_at: str = Field(default_factory=_now)
    version: int = 1
    analyzed_by: str = "mock"  # "openai" | "mock"

    name: str = ""
    tagline: str = ""
    description_short: str = ""
    description_long: str = ""
    positioning: str = ""
    icp: str = ""  # Ideal Customer Profile
    target_group: str = ""
    categories: list[str] = Field(default_factory=list)
    topics_tags: list[str] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    pricing: str = ""

    maker_name: str = ""
    maker_email: str = ""
    social_links: dict[str, str] = Field(default_factory=dict)

    assets: ProductAssets = Field(default_factory=ProductAssets)
    pages_scanned: list[str] = Field(default_factory=list)
    raw_pages: list[ScannedPage] = Field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        """Serializable view without the heavy raw page text."""
        data = self.model_dump()
        data.pop("raw_pages", None)
        return data


# ---------------------------------------------------------------------------
# Launch site registry
# ---------------------------------------------------------------------------
class Question(BaseModel):
    """A single field the launch site asks for."""

    id: str
    label: str
    type: str = "text"  # text | textarea | url | email | select | tags | file | checkbox
    maps_to: Optional[str] = None  # product attribute this field draws from
    required: bool = False
    max_length: Optional[int] = None
    help: str = ""
    options: list[str] = Field(default_factory=list)  # for select/checkbox
    # CSS selectors the extension can try, in priority order, to locate the field.
    selectors: list[str] = Field(default_factory=list)


class AuthInfo(BaseModel):
    type: str = "email"  # email | google | github | twitter | none
    signup_url: str = ""
    login_url: str = ""
    notes: str = ""


class LaunchSite(BaseModel):
    id: str
    name: str
    url: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    submit_url: str = ""
    auth: AuthInfo = Field(default_factory=AuthInfo)
    best_practices: list[str] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    fee: str = "free"  # free | paid | freemium
    do_follow: Optional[bool] = None


# ---------------------------------------------------------------------------
# Generated answers + fill plan (consumed by the extension)
# ---------------------------------------------------------------------------
class Answer(BaseModel):
    question_id: str
    label: str
    value: str
    type: str = "text"
    source: str = "product"  # product | best_practice | llm | derived | edited
    truncated: bool = False
    edited: bool = False  # user edited this value inline
    max_length: Optional[int] = None  # platform field limit (for the editor)
    help: str = ""
    selectors: list[str] = Field(default_factory=list)


class FillStep(BaseModel):
    """One concrete action for the extension's fill engine."""

    selectors: list[str]
    action: str = "fill"  # fill | select | check | click | upload
    value: str = ""
    question_id: str = ""


class AnswerSet(BaseModel):
    product_url: str
    site_id: str
    site_name: str
    generated_at: str = Field(default_factory=_now)
    generated_by: str = "mock"
    answers: list[Answer] = Field(default_factory=list)
    fill_plan: list[FillStep] = Field(default_factory=list)
    auth: AuthInfo = Field(default_factory=AuthInfo)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Drafts (persisted answer sets + agent-chat history per product)
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    at: str = Field(default_factory=_now)
    scope: str = ""  # which sites the instruction targeted, human-readable
    affected_sites: list[str] = Field(default_factory=list)


class DraftBundle(BaseModel):
    """All persisted drafts + chat history for one product URL."""

    product_url: str
    updated_at: str = Field(default_factory=_now)
    answer_sets: dict[str, AnswerSet] = Field(default_factory=dict)
    chat: list[ChatMessage] = Field(default_factory=list)
