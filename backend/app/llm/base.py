"""LLM provider interface.

Two concrete providers exist:
  * OpenAIProvider  – uses the OpenAI family of models (per the product spec).
  * MockProvider    – a deterministic, dependency-free heuristic analyzer that
                      keeps the whole product functional with no API key / network.

The provider exposes structured, product-aware methods rather than a single raw
completion so the Mock can produce genuinely useful, deterministic output.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import LaunchSite, Product, Question, ScannedPage


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def analyze_product(self, url: str, pages: list[ScannedPage]) -> dict:
        """Return a dict of product-understanding fields (name, tagline,
        positioning, icp, target_group, categories, features, benefits, ...).
        Asset extraction is handled separately by the scanner."""

    @abstractmethod
    def generate_answer(
        self,
        *,
        question: Question,
        product: Product,
        site: LaunchSite,
        best_practices: list[str],
    ) -> str:
        """Return the best-practice answer text for one launch-site question."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        """Generic text completion (used for misc. summarization tasks)."""
