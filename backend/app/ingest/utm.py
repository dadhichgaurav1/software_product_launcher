"""UTM tagging so referral traffic + conversions can be attributed per platform."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utm_url(base_url: str, site_id: str, campaign: str = "launch") -> str:
    """Return ``base_url`` with utm_source/medium/campaign set for ``site_id``.

    Existing query params are preserved; utm_* keys are overwritten.
    """
    if not base_url:
        return base_url
    parts = urlsplit(base_url if "://" in base_url else "https://" + base_url)
    query = dict(parse_qsl(parts.query))
    query.update(
        {
            "utm_source": site_id,
            "utm_medium": "launch-directory",
            "utm_campaign": campaign,
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
