# Build Plan — Agentic Software Product Launcher

## Intent (from requirements.txt)
An agentic product = **Chrome extension + web page + backend** that helps a maker
launch a software product across ~20 launch directories.

Flow:
1. User enters a product URL on the web page.
2. Backend scans the whole site, understands product (positioning, ICP, target group,
   features, benefits) and extracts assets (logo, images, videos).
3. Product is stored as well-structured JSON on the server (reused for incremental
   launches; **force refresh** rewrites it).
4. A master list of questions per launch site is maintained. The system generates
   best-practice answers per site (informed by per-platform best practices).
5. User selects which launch sites to target.
6. The Chrome extension logs in / creates an account using the user's Google account,
   fills every fillable field, and leaves it ready for manual review + submit.

## Tech decisions
- Backend: **Python + FastAPI + uvicorn** (async, great for LLM + scraping).
- LLM: provider abstraction. `OpenAIProvider` (OpenAI family, per spec) +
  deterministic `MockProvider` heuristic analyzer so the product is **fully functional
  offline** and verifiable here. Auto-selects OpenAI when `OPENAI_API_KEY` is set.
- Frontend: **vanilla HTML/CSS/JS** served by FastAPI (no build step → verifiable).
- Extension: **Manifest V3**, vanilla JS (no build step).
- Storage: JSON files on server (`backend/data/products/`), versioned, force-refresh.

## Phases
- P0  Scaffold: structure, README, configs, .gitignore.
- P1  Core: pydantic models, config, LLM abstraction (OpenAI + Mock) + tests.
- P2  Scanner: crawler + asset extractor (offline fixtures) + tests.
- P3  Analyzer + JSON store (force refresh, versioning) + tests.
- P4  Launch-site registry: master question lists + best practices + auth + selectors
      for all 20 sites (parallel sub-agents) + integrity tests.
- P5  Best-practices + answer generator → answers + fill_plan + tests.
- P6  REST API (FastAPI) + static serving + TestClient tests.
- P7  Web page frontend (URL input, product view, assets, site select, answer review,
      force refresh).
- P8  Chrome extension (MV3): manifest, background, popup, content fill-engine,
      Google-login scaffold, test page + JS tests.
- P9  End-to-end verification (pipeline e2e + live server smoke + extension JS tests).
- P10 Docs + ROADMAP (remaining items) + polish.

## Verification = functioning product
`scripts/e2e.py` runs the full pipeline on a fixture site with the Mock provider:
scan → analyze → store → select sites → generate answers + fill plans, asserting
real outputs. Live server smoke-tests all endpoints. Extension fill-engine has Node tests.

## Known-remaining (need live creds/network; framework built, noted in ROADMAP)
- Live account creation/submission on real sites (ToS, captcha, real creds).
- Real Google OAuth Gmail login inside extension (detection + scaffold built).
- Live OpenAI calls + live best-practice web research (clients built; verified via Mock).
