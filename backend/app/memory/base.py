"""Memory provider interface (sync-facing).

Two concrete providers:
  * SynapMemory – wraps the async maximem Synap SDK.
  * NullMemory  – no-op default so the product runs with no memory backend.

All methods must be resilient: a memory backend failure must never break the
launch flow (ingest swallows errors; recall returns []).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Product


class MemoryProvider(ABC):
    name: str = "base"

    # -- ingest ------------------------------------------------------------
    @abstractmethod
    def remember_product(self, product: Product) -> None:
        """Persist the understood product (name, tagline, positioning, ICP…)."""

    @abstractmethod
    def remember_edit(self, url: str, site_id: str, field_label: str, value: str) -> None:
        """Persist a user's inline edit as a durable preference/episode."""

    @abstractmethod
    def remember_instruction(self, url: str, instruction: str, scope: str, result_summary: str) -> None:
        """Persist a chat instruction (e.g. 'always lead with the benefit')."""

    @abstractmethod
    def remember_outcome(self, url: str, site_id: str, summary: str, metadata: dict) -> None:
        """Persist a post-launch outcome for a site."""

    @abstractmethod
    def remember_learnings(self, url: str, site_id: str | None, learnings: list[str]) -> None:
        """Persist after-action learnings."""

    # -- recall ------------------------------------------------------------
    @abstractmethod
    def recall(self, url: str, query: str, site_id: str | None = None, max_results: int | None = None) -> list[str]:
        """Return relevant memory snippets to ground generation (or [] )."""

    # -- meta --------------------------------------------------------------
    @abstractmethod
    def health(self) -> dict:
        """Return a small status dict for /api/health."""
