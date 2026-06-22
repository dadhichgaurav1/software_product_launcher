"""Persistent store for launches + post-launch learnings.

Per product: one ``LaunchBook`` JSON file (keyed like the product store) holding
each site's ``Launch`` (copy used + outcomes) and that product's learnings.

Cross-product feed-forward lives in a single shared ``_global_learnings.json``:
the source `learnings_for(site_id)` reads when grounding future generation. A
single-product delete never touches the shared file.
"""
from __future__ import annotations

import json

from ..config import settings
from ..models import CopySnapshot, Launch, LaunchBook, LaunchOutcome, Learning
from .product_store import product_key


class LaunchStore:
    def __init__(self, directory=None) -> None:
        self.dir = directory or (settings.data_dir / "launches")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.global_path = self.dir / "_global_learnings.json"

    def _path(self, url: str):
        return self.dir / f"{product_key(url)}.json"

    # -- per-product book --------------------------------------------------
    def load(self, url: str) -> LaunchBook:
        path = self._path(url)
        if not path.exists():
            return LaunchBook(product_url=url)
        return LaunchBook.model_validate(json.loads(path.read_text()))

    def save(self, book: LaunchBook) -> LaunchBook:
        from datetime import datetime, timezone

        book.updated_at = datetime.now(timezone.utc).isoformat()
        self._path(book.product_url).write_text(
            json.dumps(book.model_dump(), indent=2, ensure_ascii=False)
        )
        return book

    def record_launch(self, url: str, site_id: str, site_name: str, copy: CopySnapshot) -> Launch:
        book = self.load(url)
        prior = book.launches.get(site_id)
        launch = Launch(product_url=url, site_id=site_id, site_name=site_name, submitted_copy=copy)
        if prior is not None:  # keep accumulated outcomes across re-launches
            launch.outcomes = prior.outcomes
        book.launches[site_id] = launch
        self.save(book)
        return launch

    def add_outcome(self, url: str, site_id: str, outcome: LaunchOutcome) -> Launch:
        book = self.load(url)
        launch = book.launches.get(site_id)
        if launch is None:
            launch = Launch(product_url=url, site_id=site_id)
            book.launches[site_id] = launch
        launch.outcomes.append(outcome)
        if outcome.status:
            launch.status = outcome.status
        self.save(book)
        return launch

    def add_learnings(self, url: str, learnings: list[Learning]) -> None:
        if not learnings:
            return
        book = self.load(url)
        have = {ln.id for ln in book.learnings}
        new_book = [ln for ln in learnings if ln.id not in have]
        if new_book:
            book.learnings.extend(new_book)
            self.save(book)
        glob = self._load_global()
        gids = {ln.id for ln in glob}
        new_glob = [ln for ln in learnings if ln.id not in gids]
        if new_glob:
            glob.extend(new_glob)
            self._save_global(glob)

    def delete(self, url: str) -> bool:
        """Delete this product's book only — never the shared global learnings."""
        path = self._path(url)
        if path.exists():
            path.unlink()
            return True
        return False

    # -- shared global learnings (feed-forward source) ---------------------
    def learnings_for(self, site_id: str) -> list[Learning]:
        """Global learnings + those scoped to this site (cross-product)."""
        out: list[Learning] = []
        seen: set[str] = set()
        for ln in self._load_global():
            if ln.scope == "global" or ln.site_id == site_id:
                key = ln.text.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    out.append(ln)
        return out

    def _load_global(self) -> list[Learning]:
        if not self.global_path.exists():
            return []
        try:
            data = json.loads(self.global_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        return [Learning.model_validate(d) for d in data]

    def _save_global(self, items: list[Learning]) -> None:
        self.global_path.write_text(
            json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False)
        )
