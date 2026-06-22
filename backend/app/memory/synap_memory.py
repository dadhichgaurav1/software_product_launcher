"""Synap-backed memory provider.

Bridges the **async** maximem Synap SDK to the backend's sync world via a private
asyncio event loop running on a daemon thread. Every call is bounded by a timeout
and wrapped so a slow/unavailable backend degrades gracefully (ingest is swallowed,
recall returns []), never breaking the launch flow.

Scoping:
  * customer_id  = settings.synap_customer_id  (this launcher account / tenant)
  * user_id      = product_key(url)            (per-product / per-founder memory)
  * conversation = "launch:<product_key>"      (the product's launch thread)
"""
from __future__ import annotations

import asyncio
import logging
import threading

from maximem_synap import MaximemSynapSDK

from ..config import settings
from ..models import Product
from ..store.product_store import product_key
from .base import MemoryProvider

log = logging.getLogger(__name__)


class SynapMemory(MemoryProvider):
    name = "synap"

    def __init__(self) -> None:
        self._customer = settings.synap_customer_id
        self._timeout = settings.synap_timeout_s
        self._max_recall = settings.synap_max_recall
        self._initialized = False

        # Dedicated event loop on a daemon thread so we can drive the async SDK
        # from sync code (incl. FastAPI's threadpool and pytest's TestClient).
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="synap-loop", daemon=True)
        self._thread.start()

        kwargs: dict = {"api_key": settings.synap_api_key}
        if settings.synap_instance_id:
            kwargs["instance_id"] = settings.synap_instance_id
        self._sdk = MaximemSynapSDK(**kwargs)
        try:
            self._run(self._sdk.initialize())
            self._initialized = True
            log.info("Synap memory initialized (customer_id=%s)", self._customer)
        except Exception as exc:  # noqa: BLE001 - resilience by design
            log.warning("Synap initialize failed (%s); memory will no-op", exc)

    # -- async plumbing ----------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro):
        """Run a coroutine on the loop thread, bounded by the timeout."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=self._timeout)

    def _safe(self, coro, what: str):
        # NB: a timed-out future raises concurrent.futures.TimeoutError, which is
        # NOT a subclass of TimeoutError — a broad except is required here.
        try:
            return self._run(coro)
        except Exception as exc:  # noqa: BLE001
            log.debug("Synap %s degraded (%s)", what, exc)
            return None

    # -- scoping helpers ---------------------------------------------------
    @staticmethod
    def _user(url: str) -> str:
        return product_key(url)

    @staticmethod
    def _conv(url: str) -> str:
        return f"launch:{product_key(url)}"

    def _record(self, url: str, content: str, *, role: str = "user", site_id: str | None = None, kind: str | None = None) -> None:
        if not self._initialized or not content:
            return
        meta: dict = {}
        if site_id:
            meta["site_id"] = site_id
        if kind:
            meta["kind"] = kind
        self._safe(
            self._sdk.conversation.record_message(
                conversation_id=self._conv(url),
                role=role,
                content=content,
                user_id=self._user(url),
                customer_id=self._customer,
                metadata=meta or None,
            ),
            "record_message",
        )

    def _create_memory(self, url: str, document: str, *, kind: str, site_id: str | None) -> None:
        if not self._initialized or not document:
            return
        self._safe(
            self._sdk.memories.create(
                document=document,
                user_id=self._user(url),
                customer_id=self._customer,
                metadata={"kind": kind, "site_id": site_id or ""},
            ),
            f"memories.create({kind})",
        )

    # -- ingest ------------------------------------------------------------
    def remember_product(self, product: Product) -> None:
        text = (
            f"Product '{product.name}': {product.tagline}. "
            f"Positioning: {product.positioning}. ICP: {product.icp}. "
            f"Categories: {', '.join(product.categories)}. "
            f"Benefits: {'; '.join(product.benefits[:3])}."
        )
        self._record(product.url, text, role="user", kind="product")

    def remember_edit(self, url: str, site_id: str, field_label: str, value: str) -> None:
        self._record(
            url,
            f"On {site_id}, the user set the '{field_label}' field to: {value}",
            role="user", site_id=site_id, kind="edit",
        )

    def remember_instruction(self, url: str, instruction: str, scope: str, result_summary: str) -> None:
        self._record(
            url,
            f"User style instruction (applies to {scope}): {instruction}",
            role="user", kind="instruction",
        )

    def remember_outcome(self, url: str, site_id: str, summary: str, metadata: dict) -> None:
        self._create_memory(
            url, f"Launch outcome on {site_id}: {summary}", kind="outcome", site_id=site_id
        )

    def remember_learnings(self, url: str, site_id: str | None, learnings: list[str]) -> None:
        if not learnings:
            return
        scope = f" for {site_id}" if site_id else ""
        doc = f"Launch learnings{scope}:\n" + "\n".join(f"- {ln}" for ln in learnings)
        self._create_memory(url, doc, kind="learning", site_id=site_id)

    # -- recall ------------------------------------------------------------
    def recall(self, url: str, query: str, site_id: str | None = None, max_results: int | None = None) -> list[str]:
        if not self._initialized:
            return []
        resp = self._safe(
            self._sdk.fetch(
                conversation_id=self._conv(url),
                user_id=self._user(url),
                customer_id=self._customer,
                search_query=[query],
                max_results=max_results or self._max_recall,
                include_conversation_context=True,
            ),
            "fetch",
        )
        return self._to_lines(resp) if resp is not None else []

    @staticmethod
    def _to_lines(resp) -> list[str]:
        """Map a UnifiedContextResponse to a list of memory snippet strings."""
        text = None
        try:
            text = resp.format_for_prompt()
        except Exception:  # noqa: BLE001
            text = getattr(resp, "formatted_context", None)
        if text:
            lines = [ln.strip("-•* ").strip() for ln in str(text).splitlines() if ln.strip()]
            if lines:
                return lines[:50]
        # Fallback: pull content/summary off the typed memory items.
        out: list[str] = []
        for attr in ("facts", "preferences", "episodes", "temporal_events"):
            for item in getattr(resp, attr, None) or []:
                snippet = getattr(item, "content", None) or getattr(item, "summary", None)
                if snippet:
                    out.append(str(snippet))
        return out[:50]

    # -- meta --------------------------------------------------------------
    def health(self) -> dict:
        return {"provider": "synap", "enabled": self._initialized, "customer_id": self._customer}

    def close(self) -> None:
        """Stop the loop thread (used on reset to avoid thread accumulation)."""
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:  # noqa: BLE001
            pass
