"""Agent-memory layer.

Optional integration with maximem Synap that lets the launcher *remember* a
founder's product, voice/style preferences (inline edits + chat instructions)
and post-launch learnings, then *recall* them to ground future generation.

The interface is intentionally sync-facing so the rest of the (sync) backend is
unchanged; SynapMemory bridges to the async SDK internally. When no Synap key is
configured, NullMemory is used and behaviour is identical to before.
"""
from .base import MemoryProvider
from .factory import get_memory, reset_memory
from .null_memory import NullMemory

__all__ = ["MemoryProvider", "NullMemory", "get_memory", "reset_memory"]
