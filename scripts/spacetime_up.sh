#!/usr/bin/env bash
# Start SpacetimeDB (local) and publish the HiTide module. Safe to run repeatedly.
#
#   scripts/spacetime_up.sh              start local server if needed, publish (keeps data)
#   scripts/spacetime_up.sh --migrate    ...then copy existing SQLite/JSON data in (idempotent)
#   scripts/spacetime_up.sh --reset      ...wipe the database first (schema change / clean demo)
#   SPACETIME_SERVER=maincloud scripts/spacetime_up.sh   publish to Maincloud (run `spacetime login` once first)
#
# Install the CLI once:  curl -sSf https://install.spacetimedb.com | sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE="$ROOT/spacetime/floodwatch"
DB="${SPACETIME_DB:-floodwatch}"
SERVER="${SPACETIME_SERVER:-local}"
ST="$(command -v spacetime || echo "$HOME/.local/bin/spacetime")"
LOG="${TMPDIR:-/tmp}/spacetimedb-local.log"

[[ -x "$ST" ]] || { echo "spacetime CLI not found. Install: curl -sSf https://install.spacetimedb.com | sh" >&2; exit 1; }

if [[ "$SERVER" == "local" ]] && ! curl -sf -o /dev/null http://127.0.0.1:3000/v1/ping; then
  echo "starting local SpacetimeDB (log: $LOG)"
  nohup "$ST" start --listen-addr 127.0.0.1:3000 >"$LOG" 2>&1 &
  for _ in $(seq 1 40); do curl -sf -o /dev/null http://127.0.0.1:3000/v1/ping && break; sleep 0.5; done
  curl -sf -o /dev/null http://127.0.0.1:3000/v1/ping || { echo "SpacetimeDB did not start; see $LOG" >&2; exit 1; }
fi

[[ -d "$MODULE/spacetimedb/node_modules" ]] || (cd "$MODULE/spacetimedb" && npm install --silent)

DELETE=()
if [[ " $* " == *" --reset "* ]]; then
  if [[ "$SERVER" != "local" && "${CONFIRM:-0}" != "1" ]]; then
    echo "refusing to wipe '$DB' on $SERVER; re-run with CONFIRM=1 if you really mean it" >&2; exit 1
  fi
  DELETE=(--delete-data=always)
fi
(cd "$MODULE" && "$ST" publish "$DB" --server "$SERVER" -p spacetimedb ${DELETE[@]+"${DELETE[@]}"} --yes)

if [[ " $* " == *" --migrate "* ]]; then
  (cd "$ROOT/backend" && uv run python -m scripts.migrate_to_spacetime --verify)
fi

echo
echo "SpacetimeDB ready: database '$DB' on $SERVER. The backend uses it by default (HITIDE_DB_BACKEND=spacetime)."
echo "It authenticates with your spacetime CLI login, or SPACETIME_TOKEN in .env (spacetime login show --token)."
