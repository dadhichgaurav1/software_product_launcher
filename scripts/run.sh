#!/usr/bin/env bash
# Start the Software Product Launcher backend (serves the API + web page).
#
#   ./scripts/run.sh                # http://127.0.0.1:8000
#   OPENAI_API_KEY=sk-... ./scripts/run.sh   # use real OpenAI models
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../backend"

if [ "${SKIP_INSTALL:-0}" != "1" ]; then
  echo "Installing backend dependencies…"
  pip install -q -r requirements.txt
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"
echo "Starting on http://$HOST:$PORT  (web UI at /, API docs at /docs)"
# Pass through any extra args (e.g. --reload). ${1+"$@"} is the portable idiom
# so an empty arg list doesn't trip `set -u` on macOS's bash 3.2.
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" ${1+"$@"}
