"""Select and cache the active LLM provider based on configuration."""
from __future__ import annotations

import logging

from ..config import settings
from .base import LLMProvider
from .mock_provider import MockProvider

log = logging.getLogger(__name__)

_provider: LLMProvider | None = None


def get_provider(force: str | None = None) -> LLMProvider:
    """Return the active provider. ``force`` ("openai"|"mock") overrides config."""
    global _provider
    choice = (force or settings.resolved_provider())
    if _provider is not None and force is None and _provider.name == choice:
        return _provider

    if choice == "openai":
        try:
            from .openai_provider import OpenAIProvider

            provider: LLMProvider = OpenAIProvider()
            log.info("Using OpenAI provider (model=%s)", settings.llm_model)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to init OpenAI provider (%s); falling back to mock", exc)
            provider = MockProvider()
    else:
        provider = MockProvider()
        log.info("Using deterministic Mock provider (no OPENAI_API_KEY).")

    if force is None:
        _provider = provider
    return provider


def reset_provider() -> None:
    global _provider
    _provider = None
