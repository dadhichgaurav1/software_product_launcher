"""Select and cache the active memory provider based on configuration."""
from __future__ import annotations

import logging

from ..config import settings
from .base import MemoryProvider
from .null_memory import NullMemory

log = logging.getLogger(__name__)

_memory: MemoryProvider | None = None


def get_memory(force: str | None = None) -> MemoryProvider:
    """Return the active memory provider. ``force`` ("synap"|"null") overrides."""
    global _memory
    choice = force or settings.resolved_memory()
    if _memory is not None and force is None and _memory.name == choice:
        return _memory

    if choice == "synap":
        try:
            from .synap_memory import SynapMemory

            provider: MemoryProvider = SynapMemory()
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to init Synap memory (%s); using NullMemory", exc)
            provider = NullMemory()
    else:
        provider = NullMemory()

    if force is None:
        _memory = provider
    return provider


def reset_memory() -> None:
    """Drop the cached provider (and stop its loop thread if any). For tests."""
    global _memory
    if _memory is not None and hasattr(_memory, "close"):
        try:
            _memory.close()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _memory = None
