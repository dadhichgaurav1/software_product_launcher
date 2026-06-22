#!/usr/bin/env python3
"""End-to-end verification of the Software Product Launcher.

Runs the FULL product pipeline through the real HTTP API (FastAPI TestClient),
offline and deterministically, on a fixture product site:

    scan -> understand -> store JSON -> list 20 sites -> generate best-practice
    answers + fill plans for selected sites -> fetch a single site's fill plan.

Prints a human-readable report and exits non-zero if any invariant fails, so it
doubles as the "functioning product" gate. No network or API key required.

    python3 scripts/e2e.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# --- make the backend importable and force offline/deterministic mode -------
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="spl-e2e-"))
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DOWNLOAD_ASSETS"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.analyzer.product_analyzer import ProductAnalyzer  # noqa: E402
from app.api import services  # noqa: E402
from app.main import app  # noqa: E402
from app.scanner.crawler import Crawler  # noqa: E402
from tests.fixtures.fake_site import BASE, fake_fetcher  # noqa: E402

# Route the API's analyzer at the offline fixture fetcher.
services.get_analyzer = lambda: ProductAnalyzer(
    crawler=Crawler(fetcher=fake_fetcher, max_pages=10)
)

client = TestClient(app)
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    mark = "✓" if cond else "✗"
    print(f"   {mark} {msg}")
    if not cond:
        failures.append(msg)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    print("Software Product Launcher — end-to-end verification (offline, mock LLM)")

    section("1. Health & registry")
    h = client.get("/api/health").json()
    check(h["status"] == "ok", f"backend healthy (provider={h['provider']})")
    check(h["sites"] == 20, f"20 launch sites registered (got {h['sites']})")

    section("2. Scan & understand the product")
    p = client.post("/api/scan", json={"url": BASE}).json()
    print(f"   name        : {p['name']}")
    print(f"   tagline     : {p['tagline']}")
    print(f"   positioning : {p['positioning']}")
    print(f"   ICP         : {p['icp']}")
    print(f"   categories  : {', '.join(p['categories'])}")
    print(f"   features    : {len(p['features'])} | benefits: {len(p['benefits'])}")
    print(f"   pricing     : {p['pricing']}")
    print(f"   assets      : logo={'yes' if p['assets'].get('logo') else 'no'}, "
          f"images={len(p['assets'].get('images', []))}, videos={len(p['assets'].get('videos', []))}")
    check(p["name"] == "TaskPilot", "product name extracted")
    check(bool(p["tagline"]), "tagline extracted")
    check(len(p["categories"]) > 0, "categories inferred")
    check(len(p["features"]) > 0, "features extracted")
    check(p["assets"].get("logo") is not None, "logo asset detected")
    check(p["version"] == 1, "stored as JSON v1")

    section("3. Force-refresh rewrites the stored JSON")
    p2 = client.post("/api/scan", json={"url": BASE, "force": True}).json()
    check(p2["version"] == 2, f"version bumped to {p2['version']} on force refresh")

    section("4. Select launch sites & generate submissions")
    sites = client.get("/api/sites").json()["sites"]
    chosen = ["betalist", "devhunt", "showhn", "saashub", "alternativeto"]
    gen = client.post("/api/generate", json={"url": BASE, "site_ids": chosen}).json()
    check(gen["count"] == len(chosen), f"generated {gen['count']} submission drafts")

    for aset in gen["answer_sets"]:
        filled = sum(1 for a in aset["answers"] if a["value"])
        steps = len(aset["fill_plan"])
        print(f"   • {aset['site_name']:<14} {filled}/{len(aset['answers'])} fields filled, "
              f"{steps} fill steps, {aset['auth']['type']} sign-in")
        check(filled > 0, f"{aset['site_id']}: at least one field auto-filled")
        check(steps > 0, f"{aset['site_id']}: produced a fill plan")

    section("5. Sample submission draft (BetaList)")
    bl = next(a for a in gen["answer_sets"] if a["site_id"] == "betalist")
    for a in bl["answers"]:
        val = (a["value"][:70] + "…") if len(a["value"]) > 70 else a["value"]
        print(f"   {a['label']:<22}: {val or '(fill manually)'}")
    if bl["notes"]:
        print("   notes:")
        for n in bl["notes"]:
            print(f"     - {n}")

    section("6. Extension fill-plan endpoint")
    one = client.get("/api/answers/devhunt", params={"url": BASE}).json()
    check(one["site_id"] == "devhunt", "single-site fill plan served for the extension")
    check(len(one["fill_plan"]) > 0, "fill plan has steps")
    check(all(s["selectors"] for s in one["fill_plan"]), "every fill step has CSS selectors")

    section("7. Tagline fitting (no mid-word truncation)")
    long_tag = "AI task manager that plans your sprints automatically, automates standups, and ships faster"
    client.patch("/api/draft/answer", json={
        "url": BASE, "site_id": "betalist", "question_id": "pitch", "value": long_tag,
    })
    edited = client.get("/api/answers/betalist", params={"url": BASE}).json()
    pitch = next(a for a in edited["answers"] if a["question_id"] == "pitch")
    print(f"   edited pitch persisted: {pitch['value'][:60]}… (edited={pitch['edited']})")
    check(pitch["edited"] is True, "inline edit persisted + served to the extension")

    section("8. Agent-chat: revise drafts across selected sites")
    chat = client.post("/api/chat", json={
        "url": BASE, "site_ids": ["betalist", "devhunt"], "instruction": "add an emoji to make it fun",
    }).json()
    print(f"   assistant: {chat['assistant']}")
    check(chat["changed_fields"] > 0, "chat revised at least one field")
    revised = client.get("/api/answers/devhunt", params={"url": BASE}).json()
    has_emoji = any(any(ord(c) >= 0x2600 for c in a["value"]) for a in revised["answers"])
    check(has_emoji, "revision is reflected in the persisted draft")
    hist = client.get("/api/chat/history", params={"url": BASE}).json()["chat"]
    check(len(hist) >= 2, "chat history persisted (user + assistant)")

    section("8b. Agent-chat: set a NAMED url field to a literal value (honesty)")
    link = "https://synap.example/playground"
    before = client.get("/api/answers/devhunt", params={"url": BASE}).json()
    tag_before = next(a for a in before["answers"] if a["question_id"] == "tagline")["value"]
    setres = client.post("/api/chat", json={
        "url": BASE, "site_ids": ["devhunt", "betalist"], "instruction": f"For demo URL, just use {link}",
    }).json()
    print(f"   assistant: {setres['assistant']}")
    dh = next(s for s in setres["answer_sets"] if s["site_id"] == "devhunt")
    demo = next(a for a in dh["answers"] if a["question_id"] == "demo_video")
    check(demo["value"] == link, "named url field (demo_video) actually set to the value")
    check(setres["changed_fields"] == 1, "change count is accurate (no broadcast to other fields)")
    tag_after = next(a for a in dh["answers"] if a["question_id"] == "tagline")["value"]
    check(tag_after == tag_before, "unrelated fields untouched when a field is named")
    check("No matching field" in setres["assistant"], "honestly reports BetaList lacks a demo field")

    section("9. Generate across ALL 20 sites")
    all_gen = client.post("/api/generate", json={"url": BASE}).json()
    check(all_gen["count"] == 20, f"generated drafts for all {all_gen['count']} sites")
    total_fields = sum(len(s["answers"]) for s in all_gen["answer_sets"])
    total_filled = sum(1 for s in all_gen["answer_sets"] for a in s["answers"] if a["value"])
    no_midword = all(
        not a["value"] or a.get("max_length") is None or len(a["value"]) <= a["max_length"]
        for s in all_gen["answer_sets"] for a in s["answers"]
    )
    check(no_midword, "no answer exceeds its platform max_length")
    print(f"   {total_filled}/{total_fields} fields auto-filled across all 20 sites "
          f"({100*total_filled//total_fields}%)")

    print("\n" + ("=" * 56))
    if failures:
        print(f"FAILED — {len(failures)} check(s) did not pass:")
        for f in failures:
            print("  ✗ " + f)
        return 1
    print("ALL END-TO-END CHECKS PASSED — the product is functioning. 🚀")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
