#!/usr/bin/env bash
# Start backend + frontend together in one data mode.
#
#   ./dev.sh                       test data (default): simulated + cached, offline, no texts
#   ./dev.sh test                  same
#   ./dev.sh real                  live NWS/USGS feeds, live Hill Country region, live weather map; texts stay mock
#   ./dev.sh real --live-outreach  as above AND real texts/calls to the allowlisted DEMO_PHONE_* numbers
#   add --reload to restart the backend on code changes (off by default: a teammate's edit would wipe a running demo)
#
# Then open http://localhost:5173/present (Shift+D for demo controls). Ctrl-C stops both.
# Any single setting can still be overridden from the shell, e.g. REGION_MODE=replay ./dev.sh real
set -euo pipefail

MODE="${1:-test}"
LIVE_OUTREACH=0
RELOAD=()
for arg in "${@:2}"; do
  case "$arg" in
    --live-outreach) LIVE_OUTREACH=1 ;;
    --reload) RELOAD=(--reload) ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
case "$MODE" in
  test|real) ;;
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  *) echo "Usage: ./dev.sh [test|real] [--live-outreach] [--reload]" >&2; exit 2 ;;
esac
if [[ "$MODE" == "test" && "$LIVE_OUTREACH" == "1" ]]; then
  echo "--live-outreach only works with 'real'." >&2; exit 2
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"

for port in "$BACKEND_PORT" 5173; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop that process first (lsof -nP -iTCP:$port)." >&2
    exit 1
  fi
done

if [[ "$LIVE_OUTREACH" == "1" ]]; then
  printf '\033[1;31m'
  echo "REAL DATA + LIVE OUTREACH: demo runs will text and call the real DEMO_PHONE_* numbers."
  echo "Starting in 5 s. Ctrl-C to cancel."
  printf '\033[0m'
  sleep 5
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT/frontend" && npm install)
fi

export DATA_MODE="$MODE" LIVE_OUTREACH VITE_DATA_MODE="$MODE"
export VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://localhost:$BACKEND_PORT}"

cleanup() {
  trap - INT TERM EXIT
  echo "==> stopping backend and frontend"
  kill 0 2>/dev/null || true  # the whole process group: uvicorn + reloader, npm + vite, log prefixers
}
trap cleanup INT TERM EXIT

prefix() { while IFS= read -r line; do printf '%s %s\n' "$1" "$line"; done; }

(cd "$ROOT/backend" && exec uv run uvicorn app.main:app ${RELOAD[@]+"${RELOAD[@]}"} --port "$BACKEND_PORT") 2>&1 | prefix "[api]" &
(cd "$ROOT/frontend" && exec npm run dev -- --strictPort) 2>&1 | prefix "[web]" &

label="TEST DATA (offline, mock outreach)"
[[ "$MODE" == "real" ]] && label="REAL DATA (live feeds, mock outreach)"
[[ "$LIVE_OUTREACH" == "1" ]] && label="REAL DATA + LIVE TEXTS/CALLS"
echo "==> $label"
echo "==> http://localhost:5173/present   driver + console demo (Shift+D)"
echo "==> http://localhost:5173/console   ops console   (/console/inspections, /texas)"
echo "==> http://localhost:$BACKEND_PORT/api/health   shows the active modes"
echo "==> phone app (live): cd mobile && EXPO_PUBLIC_API_URL=http://localhost:$BACKEND_PORT npx expo start   (see mobile/README.md)"

wait  # until Ctrl-C (or both servers exit)
