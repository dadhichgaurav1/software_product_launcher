# Roadmap — built vs. remaining

This documents exactly what is implemented and verified, and what needs live
credentials/network (so it is scaffolded and noted rather than left silent), per
the build goal.

## ✅ Built and verified (offline, deterministic)

- **Backend (FastAPI)** — full REST API, services layer, static web hosting.
- **Website scanner** — same‑domain crawler (page‑budget, prioritised pages) +
  structured extraction (title, meta, OG, headings, lists, paragraphs, links).
- **Asset extraction** — logo, favicon, OG image, images, videos (+ optional
  local download).
- **Product understanding** — name, tagline, positioning, **ICP**, target group,
  categories, tags, features, benefits, pricing, social links. OpenAI provider +
  deterministic heuristic provider (auto‑selected).
- **Well‑structured JSON store** — one file per URL, **force refresh** rewrites &
  version‑bumps, listing, delete. Re‑used for incremental launches.
- **Launch‑site registry** — all **20 sites** with master question lists (187
  questions total), per‑field CSS selectors, auth method, fee/do‑follow, and
  curated platform best‑practices.
- **Answer + fill‑plan generation** — maps the product to every question, applies
  best‑practices, respects max‑length, resolves file fields to assets, emits the
  `fill_plan` the extension executes, plus auth + manual‑review notes.
- **Web page** — scan → review understanding/assets → select sites → review
  answers (with best‑practice/trimmed badges, notes, copy‑all).
- **Chrome extension (MV3)** — popup UI, background worker, content script, and a
  unit‑tested **fill engine** (React/Vue‑safe native value + event dispatch),
  current‑tab→site matching, and sign‑in button detection.
- **Web ↔ extension integration** — the web page **detects** the extension and
  **triggers** it (“Open & Fill”), sharing the product + backend so the extension
  pulls the *same* drafts (config auto‑synced). The launch‑site tab shows an
  in‑page Sign‑in / Fill panel — no popup, nothing re‑entered. Verified by a
  mocked‑`chrome` Node test of the message protocol.
- **Per‑task OpenAI model routing + Structured Outputs** — analyze / generate /
  revise / reason each take their own model (env‑overridable); product analysis
  uses `chat.completions.parse` with a strict‑safe Pydantic schema and degrades
  parse → JSON mode → mock. Defaults stay `gpt-4o-mini` (no invalid‑model errors);
  optimal routing + caching + service‑tier are opt‑in. Offline unit‑tested.
- **Agent memory (Synap)** — optional `MemoryProvider` (NullMemory default) that
  remembers the product, inline edits and chat style‑instructions and recalls them
  to ground generation. SynapMemory bridges the async maximem‑synap SDK to the
  sync backend with bounded timeouts and graceful degradation. Offline‑tested with
  a fake async SDK; `scripts/synap_smoke.py` is the live round‑trip.
- **Post‑launch learning loop** — capture the submitted copy, log an outcome
  (manual / Show‑HN API / UTM), run after‑action reasoning to derive learnings,
  and **feed them into the best‑practices for the next generation** (loop closed,
  proven by a test that spies on the practices into the next generate). Endpoints
  `/api/launch`, `/api/outcome`, `/api/launches`, `/api/learnings`; a web “After
  launch” panel; per‑product + shared global learning stores.
- **Tests** — `pytest` suite (66) + `scripts/e2e.py` (full pipeline incl. the
  learning loop) + Node tests for the fill engine and the web↔extension protocol.

## 🚧 Remaining — needs live credentials/network (scaffolded + noted)

1. **Live account creation & submission on the real sites.**
   By design the extension fills fields and **stops before submitting**
   (requirement: *"ready for the user to manually review and submit"*). Wiring an
   optional auto‑submit per site is a small addition but intentionally left off.

2. **Google/Gmail (and GitHub) sign‑in automation.**
   Browsers block scripted credential entry; OAuth + CAPTCHA must be completed by
   the user. The extension **detects and clicks** the "Sign in with Google/GitHub"
   button, then hands off. Full headless OAuth would require the user's session
   and is out of scope for a review‑then‑submit tool.

3. **Live OpenAI generation.**
   `OpenAIProvider` is implemented (Structured‑Outputs analysis + per‑task model
   routing + per‑field generation with graceful fallback). It is verified here via
   the deterministic mock because this environment has **no key and no outbound
   network**. Set `OPENAI_API_KEY` (and optionally the `LLM_MODEL_*` routing vars)
   to enable production‑grade copy — no code change needed.

   **Live Synap memory** is likewise implemented and offline‑tested; set
   `SYNAP_API_KEY` and run `scripts/synap_smoke.py` for the live round‑trip.

4. **Live best‑practice research** (search communities/blogs + each launch site's
   own page). A pluggable `live_researcher` hook is implemented and wired into the
   generator; it activates automatically with a real LLM/network. Offline, the
   curated per‑site best‑practices are used.

5. **File uploads** (logo/screenshots). Browsers do not allow scripted file
   selection. The extension highlights the field and surfaces the suggested asset
   path/URL for a one‑click manual attach.

6. **CSS selector calibration.** Because the 20 live sites can't be browsed from
   this environment, each site's selectors are realistic **best‑effort** guesses
   (2–3 fallbacks per field). Recommended next step: a calibration pass that opens
   each site, records the real DOM selectors, and updates the registry JSON.

7. **Extension icons.** ✅ Real PNG icons (16/48/128) are generated and committed
   in `extension/icons/` (Chrome refuses to load the manifest if a referenced icon
   is missing). Regenerate or swap them per `extension/icons/README.md`.

## Extending

- **Add a launch site:** drop a `backend/app/registry/data/<id>.json` matching the
  `LaunchSite` schema — it's picked up automatically (validated on load).
- **Swap the LLM:** implement `LLMProvider` and register it in `llm/factory.py`.
- **Calibrate selectors:** edit the `selectors` arrays in each site JSON.
