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

    # Per-task model routing. Each defaults to LLM_MODEL so out-of-the-box
    # behaviour is unchanged (and the default is a known-valid model id — no
    # accidental 404s). Override per task for optimal cost/quality, e.g.
    # LLM_MODEL_ANALYZE=gpt-5.4, LLM_MODEL_GENERATE=gpt-5.4-mini, etc.
    llm_model_analyze: str = os.getenv("LLM_MODEL_ANALYZE", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_model_generate: str = os.getenv("LLM_MODEL_GENERATE", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_model_revise: str = os.getenv("LLM_MODEL_REVISE", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_model_reason: str = os.getenv("LLM_MODEL_REASON", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    # "" => not sent. One of: auto | default | flex | scale | priority.
    llm_service_tier: str = os.getenv("LLM_SERVICE_TIER", "")
    llm_prompt_cache_key: str = os.getenv("LLM_PROMPT_CACHE_KEY", "")
    # Use OpenAI Structured Outputs (chat.completions.parse) for analysis.
    llm_structured_outputs: bool = _bool("LLM_STRUCTURED_OUTPUTS", True)

    # --- Memory (Synap) ----------------------------------------------------
    # Optional agent-memory layer (maximem Synap). When no key is present the
    # NullMemory provider is used and the product behaves exactly as before.
    synap_api_key: str | None = os.getenv("SYNAP_API_KEY")
    synap_instance_id: str = os.getenv("SYNAP_INSTANCE_ID", "")
    synap_customer_id: str = os.getenv("SYNAP_CUSTOMER_ID", "software-product-launcher")
    synap_timeout_s: int = _int("SYNAP_TIMEOUT_S", 6)
    synap_max_recall: int = _int("SYNAP_MAX_RECALL", 8)
    # "synap" | "null" | "auto"
    memory_provider: str = os.getenv("MEMORY_PROVIDER", "auto").lower()

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

    def resolved_memory(self) -> str:
        """Decide which memory provider to use given config + key availability."""
        if self.memory_provider in {"synap", "null"}:
            return self.memory_provider
        return "synap" if self.synap_api_key else "null"

    def model_for(self, task: str) -> str:
        """Return the configured model id for a task ("analyze"|"generate"|
        "revise"|"reason"), falling back to the global default."""
        return {
            "analyze": self.llm_model_analyze,
            "generate": self.llm_model_generate,
            "revise": self.llm_model_revise,
            "reason": self.llm_model_reason,
        }.get(task, self.llm_model)

    def ensure_dirs(self) -> None:
        self.products_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
