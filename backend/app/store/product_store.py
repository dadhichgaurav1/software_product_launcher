"""Persistent JSON store for analyzed products.

One JSON file per product URL (keyed by a normalized hash). Supports load/save,
existence checks, listing summaries, version bumping on force-refresh, and delete.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from ..config import settings
from ..models import Product


def product_key(url: str) -> str:
    """Stable, scheme/www/trailing-slash-insensitive key for a product URL."""
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/").lower()
    norm = f"{host}{path}"
    digest = hashlib.sha1(norm.encode()).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:40] or "product"
    return f"{slug}-{digest}"


class ProductStore:
    def __init__(self, directory=None) -> None:
        self.dir = directory or settings.products_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str):
        return self.dir / f"{product_key(url)}.json"

    def exists(self, url: str) -> bool:
        return self._path(url).exists()

    def load(self, url: str) -> Product | None:
        path = self._path(url)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Product.model_validate(data)

    def save(self, product: Product, *, force: bool = False) -> Product:
        """Persist a product. On overwrite, bump version (keeps history count)."""
        existing = self.load(product.url)
        if existing is not None:
            product.version = existing.version + 1 if force else existing.version
        path = self._path(product.url)
        path.write_text(json.dumps(product.model_dump(), indent=2, ensure_ascii=False))
        return product

    def delete(self, url: str) -> bool:
        path = self._path(url)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_summaries(self) -> list[dict]:
        out: list[dict] = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            out.append(
                {
                    "url": data.get("url", ""),
                    "name": data.get("name", ""),
                    "tagline": data.get("tagline", ""),
                    "fetched_at": data.get("fetched_at", ""),
                    "version": data.get("version", 1),
                    "analyzed_by": data.get("analyzed_by", ""),
                    "key": path.stem,
                }
            )
        return out
