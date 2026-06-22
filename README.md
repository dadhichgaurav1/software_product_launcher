# 🚀 Software Product Launcher

An **agentic launcher** that takes the URL of a software product, understands it,
and prepares submissions across **20 launch directories** — leaving each form
filled and ready for you to review and submit.

It has the three components called for in the brief ([`requirements.txt`](requirements.txt)):

| Component | Role |
|-----------|------|
| **Backend** (`backend/`, FastAPI) | Scans the site, understands the product, stores it as JSON, hosts the registry of launch sites, and generates best‑practice answers + fill plans. Runs the agent. |
| **Web page** (`frontend/`, vanilla SPA) | Enter a URL, review the understood product + assets, pick launch sites, review the generated answers. |
| **Chrome extension** (`extension/`, MV3) | On each launch site, auto‑fills the form from the backend's fill plan and assists with Google/GitHub sign‑in. Leaves it ready for manual submit. |

> The brief says *"assume the LLM API key to be present from the OpenAI family."*
> The backend uses OpenAI when `OPENAI_API_KEY` is set, and otherwise falls back
> to a **deterministic heuristic analyzer** so the whole product runs, and is
> verifiable, with no key or network. Set the key for production‑grade copy.

---

## The execution sequence

This is the "right sequence of execution" derived from the requirements:

1. **Input** — user enters a product URL on the web page.
2. **Scan** — backend crawls the site (same‑domain, prioritising
   features/pricing/about pages).
3. **Understand** — LLM (or heuristic) extracts name, tagline, positioning,
   **ICP**, target group, categories, features, benefits, pricing, socials.
4. **Assets** — logo, favicon, images and videos are extracted (and optionally
   downloaded).
5. **Store** — saved as a well‑structured JSON per URL
   (`backend/data/products/`). Re‑used for incremental launches; **force refresh**
   re‑writes it and bumps the version.
6. **Select** — user picks which of the 20 launch sites to target.
7. **Answer** — for each site's master question list, the backend generates
   answers that follow that **platform's best‑practices** (curated per site +
   tag‑based + general + optional live research), fitting each field to its
   exact length limit at a clean word/clause boundary (no mid‑word chops),
   and builds a **fill plan** (CSS selectors + values).
8. **Refine** — every field is **editable inline** (auto‑saved), and an
   **agent chat** iterates on the drafts across all selected sites (e.g. “make
   all taglines punchier”, “lead with the benefit”, “add an emoji”). Edits and
   revisions persist and feed the fill plan.
9. **Fill** — click **“Open & Fill”** on a site (or **“Open & fill all”**) right
   from the web page: it opens the launch site and **triggers the extension**,
   sharing the product + backend so it pulls the *same* drafts (no popup, no
   re-entering anything). The launch-site tab shows an in-page panel to **sign in**
   (Google/GitHub/email) and **fill every field**, left **ready for manual review
   and submit**.

---

## Quickstart

### 1. Run the backend (serves the API **and** the web page)

```bash
./scripts/run.sh                      # http://127.0.0.1:8000
# or, for real OpenAI copy:
OPENAI_API_KEY=sk-... ./scripts/run.sh
```

Or manually:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/** for the web page, **/docs** for the API.

### 2. Load the Chrome extension

1. `chrome://extensions` → enable **Developer mode**.
2. **Load unpacked** → select the `extension/` folder.
3. Reload the web page (`http://127.0.0.1:8000`). It shows **“Extension
   connected”** — the page and extension now share the session automatically.
4. Scan → Generate, then click **“Open & Fill”** on any site. Its tab opens with
   an in-page **Sign in** / **Fill this page** panel — no popup, nothing to
   re-enter. (The popup still works as a manual fallback.)

See [`extension/README.md`](extension/README.md) for details.

---

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | – | Enables the OpenAI provider (else deterministic mock). |
| `LLM_MODEL` | `gpt-4o-mini` | Default model id; the per‑task models below fall back to it. |
| `LLM_MODEL_ANALYZE` | `=LLM_MODEL` | Model for product understanding (highest‑value call). |
| `LLM_MODEL_GENERATE` | `=LLM_MODEL` | Model for per‑field copy generation (highest volume). |
| `LLM_MODEL_REVISE` | `=LLM_MODEL` | Model for agent‑chat revisions. |
| `LLM_MODEL_REASON` | `=LLM_MODEL` | Model for post‑launch after‑action learnings. |
| `LLM_SERVICE_TIER` | – | OpenAI service tier (cost control); omitted when unset. |
| `LLM_PROMPT_CACHE_KEY` | – | Optional prompt‑cache key for the shared prefix. |
| `LLM_STRUCTURED_OUTPUTS` | `true` | Use Structured Outputs (`chat.completions.parse`) for analysis. |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `mock`. |
| `OPENAI_BASE_URL` | – | Optional OpenAI‑compatible endpoint. |
| `SYNAP_API_KEY` | – | Enables the Synap memory layer (else NullMemory; behaviour unchanged). |
| `SYNAP_CUSTOMER_ID` | `software-product-launcher` | Tenant scope for Synap memories. |
| `MEMORY_PROVIDER` | `auto` | `auto` \| `synap` \| `null`. |
| `DATA_DIR` | `backend/data` | Where product JSON + assets are stored. |
| `CRAWL_MAX_PAGES` | `12` | Page budget per scan. |
| `DOWNLOAD_ASSETS` | `true` | Download logos/images locally. |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Server bind. |

### Recommended OpenAI model routing (opt‑in)

Defaults stay on `gpt-4o-mini` everywhere so there are **no invalid‑model errors
out of the box**. Route by task for optimal cost/quality — each call type has its
own env var, so you change models without touching code:

| Task | Env var | Recommended | Why |
|------|---------|-------------|-----|
| Understand the product | `LLM_MODEL_ANALYZE` | `gpt-5.4` / `gpt-5.5` | One call per product; everything downstream depends on it. Structured Outputs. |
| Per‑field copy | `LLM_MODEL_GENERATE` | `gpt-5.4-mini` (long‑tail `gpt-4.1-nano`) | ~187 short, length‑capped calls; cache the shared prefix, batch "generate all". |
| Agent‑chat revisions | `LLM_MODEL_REVISE` | `gpt-5.4-mini` | Interactive, latency‑sensitive, low volume. |
| Post‑launch learnings | `LLM_MODEL_REASON` | `o4-mini` | Benefits from reasoning; runs once per outcome. |

---

## Memory (Synap) & the post‑launch learning loop

Two capabilities make the launcher **stateful and compounding** rather than
one‑shot. Both are optional and degrade cleanly — with no `SYNAP_API_KEY` and no
logged outcomes, the product behaves exactly as before.

- **Agent memory (Synap).** With `SYNAP_API_KEY` set, the launcher *remembers*
  the product, your inline edits, and your chat style‑instructions (e.g. “always
  lead with the benefit”), then *recalls* them to ground future generation — so a
  preference said once is applied across all sites and future launches. Scopes:
  `customer_id` = your account, `user_id` = the product, conversation =
  `launch:<product>`. It uses `conversation.record_message` for episodes and
  `memories.create` for outcomes/learnings; recall via `sdk.fetch`. The async SDK
  is bridged to the sync backend with bounded timeouts, so a slow/unavailable
  backend never blocks a launch.
- **Post‑launch learning loop.** After you submit, **log the outcome** (upvotes,
  rank, signups, status) from the web page’s *“After launch”* panel (or
  `POST /api/outcome`). The backend runs an after‑action reasoning pass to derive
  1–3 reusable **learnings**, persists them (per‑product + a shared global store),
  and **feeds them into the best‑practices** that ground the next generation for
  that platform — closing the loop. Outcomes can be user‑reported (offline) or
  ingested from public sources (Show HN via the HN Algolia API; UTM‑tagged links
  for referral/conversion attribution).

```
scan → generate → fill → submit → log outcome → reason → learn → feeds next generate
```

---

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Status, active LLM + memory provider, site count. |
| `GET` | `/api/sites` | List all 20 launch sites (summaries). |
| `GET` | `/api/sites/{id}` | Full site definition (questions, best practices, auth). |
| `POST` | `/api/scan` | `{url, force}` → scan/understand/store; returns product JSON. |
| `GET` | `/api/products` | List stored products. |
| `GET` | `/api/product?url=` | Fetch a stored product. |
| `DELETE` | `/api/product?url=` | Delete a stored product (+ its drafts & launch book). |
| `POST` | `/api/generate` | `{url, site_ids?, force_scan?, regenerate?}` → answer sets + fill plans (persisted as drafts). |
| `GET` | `/api/answers/{site_id}?url=` | Single site's draft/fill plan (used by the extension; serves edits). |
| `GET` | `/api/drafts?url=` | All persisted drafts + chat history for a product. |
| `PATCH` | `/api/draft/answer` | `{url, site_id, question_id, value}` → inline-edit one field; rebuilds its fill step. |
| `POST` | `/api/chat` | `{url, instruction, site_ids?}` → agent-chat revises drafts across sites. |
| `GET` | `/api/chat/history?url=` | Persisted agent-chat transcript. |
| `POST` | `/api/launch` | `{url, site_id}` → snapshot the copy being submitted (start of a launch). |
| `POST` | `/api/outcome` | `{url, site_id, status?, points?, rank?, signups?, …}` → log an outcome; returns derived learnings. |
| `GET` | `/api/launches?url=` | A product's launch book (launches + outcomes + learnings). |
| `GET` | `/api/learnings?url=&site_id=` | Learnings for a product (+ the feed‑forward set for a site). |

---

## The 20 launch sites

LaunchPad India · BetaList · Uneed · Peerlist Launchpad · Fazier · DevHunt ·
Show HN · MicroLaunch · SmolLaunch · TinyStartups · TinyLaunch · StartupBase ·
Indie Hackers · LaunchingNext · OpenHunts · Firsto · PitchWall · LaunchIgniter ·
SaaSHub · AlternativeTo.

Each is defined in `backend/app/registry/data/<id>.json` with its master question
list, field selectors, auth method, fee/do‑follow, and platform best‑practices.

---

## Testing & verification

```bash
cd backend && python3 -m pytest        # unit + API tests (offline, deterministic)
python3 scripts/e2e.py                 # full pipeline through the HTTP API (offline)
node extension/test/fill_engine.test.js  # extension fill-engine tests
node extension/test/bridge.test.js       # web↔extension protocol tests
SYNAP_API_KEY=sk-... python3 scripts/synap_smoke.py  # live Synap round-trip (optional)
```

`scripts/e2e.py` is the "functioning product" gate: it scans a fixture product,
understands it, stores it, lists the 20 sites, generates answers + fill plans for
every site, exercises the agent‑chat, **and runs the full post‑launch learning
loop** (log an outcome → derive learnings → feed them into the next generation) —
all deterministically and offline. `scripts/synap_smoke.py` is the live
end‑to‑end check for the memory layer once a `SYNAP_API_KEY` is set (it prints
`SYNAP DISABLED` and exits 0 without one).

---

## Project structure

```
backend/
  app/
    config.py            settings (env-overridable)
    models.py            Product JSON, LaunchSite, AnswerSet/FillPlan schemas
    llm/                 provider abstraction: openai_provider, mock_provider, factory
    memory/              Synap agent-memory layer (base, null, synap, factory)
    scanner/             crawler + asset extractor
    analyzer/            product analyzer (scan → understanding → Product)
    store/               product + draft + launch JSON stores
    registry/            launch-site registry + data/<id>.json (20 sites)
    answers/             best_practices + answer/fill-plan generator
    ingest/              post-launch outcome ingestion (HN Algolia, UTM)
    api/                 FastAPI routes + services layer
    main.py              app entry (API + static web page)
  tests/                 pytest suite (offline)
frontend/                vanilla HTML/CSS/JS web page
extension/               Manifest V3 Chrome extension
scripts/                 run.sh, e2e.py
requirements.txt         the product brief (spec)
PLAN.md                  build plan
ROADMAP.md               what's done + what remains (and why)
```

See [`ROADMAP.md`](ROADMAP.md) for what is fully built versus what needs live
credentials/network (and is therefore scaffolded + noted).
