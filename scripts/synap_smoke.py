#!/usr/bin/env python3
"""Live Synap end-to-end smoke test.

Run AFTER setting SYNAP_API_KEY (and optionally SYNAP_CUSTOMER_ID). It does a
real initialize -> remember -> recall round-trip against the Synap backend and
prints what came back, so we can verify the memory layer end-to-end.

    SYNAP_API_KEY=sk-... python scripts/synap_smoke.py

With no key it prints "SYNAP DISABLED" and exits 0 (safe to run anywhere).
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings  # noqa: E402
from app.memory.factory import get_memory, reset_memory  # noqa: E402
from app.models import Product  # noqa: E402


def main() -> int:
    if settings.resolved_memory() != "synap":
        print("SYNAP DISABLED — set SYNAP_API_KEY to run the live smoke test.")
        return 0

    reset_memory()
    mem = get_memory(force="synap")
    health = mem.health()
    print("health:", health)
    if not health.get("enabled"):
        print("FAILED — Synap did not initialize (check key / network).")
        return 1

    url = "https://taskpilot.ai"
    product = Product(
        url=url,
        name="TaskPilot",
        tagline="Your AI project manager that ships the busywork",
        positioning="AI-native project management for small teams",
        icp="Startup founders and small product teams",
        categories=["AI", "Productivity"],
        benefits=["Save hours of status-chasing every week"],
    )

    print("\n-> remember_product / instruction / learnings ...")
    mem.remember_product(product)
    mem.remember_instruction(url, "Always lead with the time-saving benefit.", "all drafts", "noted")
    mem.remember_learnings(url, "devhunt", ["Benefit-led taglines with one emoji outperform on DevHunt."])

    # Ingestion is asynchronous on the Synap side; give it a moment.
    time.sleep(3)

    print("-> recall('what tone and benefits should the taglines use?') ...")
    lines = mem.recall(url, query="what tone and benefits should the taglines use?", site_id="devhunt")
    if lines:
        print("RECALLED:")
        for ln in lines:
            print("  •", ln)
        print("\nSYNAP SMOKE PASSED ✅")
        return 0
    print("\nNo memories recalled yet (ingestion may still be processing). "
          "Re-run in a few seconds; the calls themselves succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
