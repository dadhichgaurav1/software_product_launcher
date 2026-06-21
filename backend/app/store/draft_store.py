"""Persistent store for generated drafts + agent-chat history, per product URL.

One JSON file per product (keyed like the product store) holding every site's
AnswerSet plus the chat transcript, so inline edits and chat revisions persist
and feed the extension's fill plan.
"""
from __future__ import annotations

import json

from ..config import settings
from ..models import AnswerSet, ChatMessage, DraftBundle
from .product_store import product_key


class DraftStore:
    def __init__(self, directory=None) -> None:
        self.dir = directory or (settings.data_dir / "drafts")
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str):
        return self.dir / f"{product_key(url)}.json"

    def load(self, url: str) -> DraftBundle:
        path = self._path(url)
        if not path.exists():
            return DraftBundle(product_url=url)
        return DraftBundle.model_validate(json.loads(path.read_text()))

    def save(self, bundle: DraftBundle) -> DraftBundle:
        from datetime import datetime, timezone

        bundle.updated_at = datetime.now(timezone.utc).isoformat()
        self._path(bundle.product_url).write_text(
            json.dumps(bundle.model_dump(), indent=2, ensure_ascii=False)
        )
        return bundle

    def delete(self, url: str) -> bool:
        path = self._path(url)
        if path.exists():
            path.unlink()
            return True
        return False

    # -- convenience -------------------------------------------------------
    def put_sets(self, url: str, sets: list[AnswerSet]) -> DraftBundle:
        bundle = self.load(url)
        for s in sets:
            bundle.answer_sets[s.site_id] = s
        return self.save(bundle)

    def get_set(self, url: str, site_id: str) -> AnswerSet | None:
        return self.load(url).answer_sets.get(site_id)

    def append_chat(self, url: str, *messages: ChatMessage) -> DraftBundle:
        bundle = self.load(url)
        bundle.chat.extend(messages)
        return self.save(bundle)
