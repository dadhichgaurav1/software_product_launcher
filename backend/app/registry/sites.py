"""Launch-site registry loader.

Each launch site is a JSON file under ``registry/data/<id>.json`` validated
against the LaunchSite schema. The registry loads, validates and caches them and
exposes lookups used by the answer generator and the API.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..models import LaunchSite

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"

# Product attributes a question may map to. ``None``/"" means a custom field the
# answer generator fills from best practices rather than a direct product field.
VALID_MAPS_TO = {
    "name", "tagline", "description_short", "description_long", "positioning",
    "icp", "target_group", "categories", "topics_tags", "features", "benefits",
    "pricing", "url", "maker_name", "maker_email", "twitter", "github", "linkedin",
}

_cache: dict[str, LaunchSite] | None = None


def _load_all(directory: Path = DATA_DIR) -> dict[str, LaunchSite]:
    sites: dict[str, LaunchSite] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            site = LaunchSite.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            log.error("Invalid launch-site file %s: %s", path.name, exc)
            raise
        if site.id in sites:
            raise ValueError(f"Duplicate launch-site id '{site.id}' in {path.name}")
        sites[site.id] = site
    return sites


def all_sites(refresh: bool = False) -> list[LaunchSite]:
    global _cache
    if _cache is None or refresh:
        _cache = _load_all()
    return list(_cache.values())


def get_site(site_id: str) -> LaunchSite | None:
    if _cache is None:
        all_sites()
    return (_cache or {}).get(site_id)


def site_ids() -> list[str]:
    return [s.id for s in all_sites()]


def validate_registry() -> list[str]:
    """Return a list of human-readable validation problems (empty == all good)."""
    problems: list[str] = []
    for site in all_sites(refresh=True):
        if not site.questions:
            problems.append(f"{site.id}: no questions defined")
        ids = [q.id for q in site.questions]
        if len(ids) != len(set(ids)):
            problems.append(f"{site.id}: duplicate question ids")
        for q in site.questions:
            if q.maps_to and q.maps_to not in VALID_MAPS_TO:
                problems.append(f"{site.id}.{q.id}: invalid maps_to '{q.maps_to}'")
            if q.type not in {
                "text", "textarea", "url", "email", "select", "tags",
                "file", "checkbox", "number",
            }:
                problems.append(f"{site.id}.{q.id}: invalid type '{q.type}'")
    return problems
