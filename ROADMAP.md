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
- **Tests** — `pytest` suite + `scripts/e2e.py` (full pipeline through the HTTP
  API) + Node test for the fill engine.

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
   `OpenAIProvider` is implemented (JSON‑mode analysis + per‑field generation with
   graceful fallback). It is verified here via the deterministic mock because this
   environment has **no key and no outbound network**. Set `OPENAI_API_KEY` to
   enable production‑grade copy — no code change needed.

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

7. **Extension icons.** Placeholder note in `extension/icons/`; Chrome shows a
   default icon until real PNGs are added.

## Extending

- **Add a launch site:** drop a `backend/app/registry/data/<id>.json` matching the
  `LaunchSite` schema — it's picked up automatically (validated on load).
- **Swap the LLM:** implement `LLMProvider` and register it in `llm/factory.py`.
- **Calibrate selectors:** edit the `selectors` arrays in each site JSON.
