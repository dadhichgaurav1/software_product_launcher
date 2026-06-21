"""Central configuration for the Software Product Launcher backend.

All settings are environment-overridable so the app can run locally on a
developer's machine or hosted, per the product requirements.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo layout: <repo>/backend/app/config.py  ->  BACKEND_DIR = <repo>/backend
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
FRONTEND_DIR = REPO_DIR / "frontend"


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """Runtime settings, resolved from environment variables with sane defaults."""

    # --- LLM ---------------------------------------------------------------
    # Per spec, assume an OpenAI-family key. When absent we fall back to the
    # deterministic Mock provider so the product is fully functional offline.
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")  # optional override
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    # Force a provider regardless of key presence: "openai" | "mock" | "auto"
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto").lower()

    # --- Storage -----------------------------------------------------------
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data")))

    @property
    def products_dir(self) -> Path:
        return self.data_dir / "products"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    # --- Crawler -----------------------------------------------------------
    crawl_max_pages: int = _int("CRAWL_MAX_PAGES", 12)
    crawl_timeout_s: int = _int("CRAWL_TIMEOUT_S", 15)
    crawl_user_agent: str = os.getenv(
        "CRAWL_USER_AGENT",
        "SoftwareProductLauncherBot/1.0 (+https://github.com/)",
    )
    download_assets: bool = _bool("DOWNLOAD_ASSETS", True)
    max_asset_bytes: int = _int("MAX_ASSET_BYTES", 8 * 1024 * 1024)

    # --- Server ------------------------------------------------------------
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = _int("PORT", 8000)

    def resolved_provider(self) -> str:
        """Decide which LLM provider to use given config + key availability."""
        if self.llm_provider in {"openai", "mock"}:
            return self.llm_provider
        # auto
        return "openai" if self.openai_api_key else "mock"

    def ensure_dirs(self) -> None:
        self.products_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
