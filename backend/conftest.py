"""Pytest bootstrap: make the ``app`` package importable and isolate the data dir."""
import os
import sys
import tempfile
from pathlib import Path

# Ensure `backend/` is on sys.path so `import app...` works from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Route the runtime data store to a throwaway temp dir during tests.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="spl-test-data-"))
# Force the deterministic provider so tests never depend on network/keys.
os.environ.setdefault("LLM_PROVIDER", "mock")
# Never reach the network to download assets during tests.
os.environ.setdefault("DOWNLOAD_ASSETS", "false")
