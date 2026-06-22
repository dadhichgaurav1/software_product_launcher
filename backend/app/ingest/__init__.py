"""Post-launch outcome ingestion (public APIs + analytics tagging).

These are network-gated and use injectable fetchers so they're offline-testable
(mirroring the website crawler). Offline, outcomes are user-reported via the API.
"""
from .hn import fetch_hn_outcome
from .utm import utm_url

__all__ = ["fetch_hn_outcome", "utm_url"]
