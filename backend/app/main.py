"""FastAPI application entry point.

Serves the JSON API and the static web page. Run locally with:
    uvicorn app.main:app --reload    (from the backend/ directory)
or via the helper script: ../scripts/run.sh
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .llm.factory import get_provider
from .registry import sites as registry
from .api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("launcher")

app = FastAPI(
    title="Software Product Launcher",
    version="1.0.0",
    description="Agentic launcher: scan a product site, understand it, and fill "
    "submission forms across 20 launch directories.",
)

# The Chrome extension and a separately served frontend need cross-origin access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def _startup() -> None:
    settings.ensure_dirs()
    problems = registry.validate_registry()
    if problems:
        for p in problems:
            log.warning("registry problem: %s", p)
    log.info(
        "Launcher ready: provider=%s, sites=%d, data=%s",
        get_provider().name,
        len(registry.all_sites()),
        settings.data_dir,
    )


# -- static frontend --------------------------------------------------------
@app.get("/")
def index():
    from .config import FRONTEND_DIR

    target = FRONTEND_DIR / "index.html"
    if target.exists():
        return FileResponse(str(target))
    return JSONResponse({"message": "Software Product Launcher API. See /docs."})


def _mount_static() -> None:
    from .config import FRONTEND_DIR

    if FRONTEND_DIR.exists():
        app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        # Serve assets (downloaded logos/images) for preview in the UI.
        settings.ensure_dirs()
        app.mount("/assets", StaticFiles(directory=str(settings.assets_dir)), name="assets")


_mount_static()
