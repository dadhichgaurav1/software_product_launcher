"""No-op memory provider — the default when no Synap key is configured."""
from __future__ import annotations

from ..models import Product
from .base import MemoryProvider


class NullMemory(MemoryProvider):
    name = "null"

    def remember_product(self, product: Product) -> None:
        pass

    def remember_edit(self, url: str, site_id: str, field_label: str, value: str) -> None:
        pass

    def remember_instruction(self, url: str, instruction: str, scope: str, result_summary: str) -> None:
        pass

    def remember_outcome(self, url: str, site_id: str, summary: str, metadata: dict) -> None:
        pass

    def remember_learnings(self, url: str, site_id: str | None, learnings: list[str]) -> None:
        pass

    def recall(self, url: str, query: str, site_id: str | None = None, max_results: int | None = None) -> list[str]:
        return []

    def health(self) -> dict:
        return {"provider": "null", "enabled": False}
