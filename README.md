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
9. **Fill** — the Chrome extension signs in (or creates an account) with the
   user's Google/GitHub/email, fills every fillable field, and leaves the form
   **ready for manual review and submit**.

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
3. Open the popup → set the Backend URL (default `http://127.0.0.1:8000`) and
   your product URL.
4. Visit a launch site, open the popup, and click **Fill This Page**.

See [`extension/README.md`](extension/README.md) for details.

---

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | – | Enables the OpenAI provider (else deterministic mock). |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model id. |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `mock`. |
| `OPENAI_BASE_URL` | – | Optional OpenAI‑compatible endpoint. |
| `DATA_DIR` | `backend/data` | Where product JSON + assets are stored. |
| `CRAWL_MAX_PAGES` | `12` | Page budget per scan. |
| `DOWNLOAD_ASSETS` | `true` | Download logos/images locally. |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Server bind. |

---

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Status, active provider, site count. |
| `GET` | `/api/sites` | List all 20 launch sites (summaries). |
| `GET` | `/api/sites/{id}` | Full site definition (questions, best practices, auth). |
| `POST` | `/api/scan` | `{url, force}` → scan/understand/store; returns product JSON. |
| `GET` | `/api/products` | List stored products. |
| `GET` | `/api/product?url=` | Fetch a stored product. |
| `DELETE` | `/api/product?url=` | Delete a stored product. |
| `POST` | `/api/generate` | `{url, site_ids?, force_scan?, regenerate?}` → answer sets + fill plans (persisted as drafts). |
| `GET` | `/api/answers/{site_id}?url=` | Single site's draft/fill plan (used by the extension; serves edits). |
| `GET` | `/api/drafts?url=` | All persisted drafts + chat history for a product. |
| `PATCH` | `/api/draft/answer` | `{url, site_id, question_id, value}` → inline-edit one field; rebuilds its fill step. |
| `POST` | `/api/chat` | `{url, instruction, site_ids?}` → agent-chat revises drafts across sites. |
| `GET` | `/api/chat/history?url=` | Persisted agent-chat transcript. |

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
cd backend && python3 -m pytest        # unit + API tests
python3 scripts/e2e.py                 # full pipeline through the HTTP API (offline)
node extension/test/fill_engine.test.js  # extension fill-engine tests
```

`scripts/e2e.py` is the "functioning product" gate: it scans a fixture product,
understands it, stores it, lists the 20 sites, and generates answers + fill plans
for every site — all deterministically and offline.

---

## Project structure

```
backend/
  app/
    config.py            settings (env-overridable)
    models.py            Product JSON, LaunchSite, AnswerSet/FillPlan schemas
    llm/                 provider abstraction: openai_provider, mock_provider, factory
    scanner/             crawler + asset extractor
    analyzer/            product analyzer (scan → understanding → Product)
    store/               JSON product store (force refresh, versioning)
    registry/            launch-site registry + data/<id>.json (20 sites)
    answers/             best_practices + answer/fill-plan generator
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
