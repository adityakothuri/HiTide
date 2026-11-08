#!/usr/bin/env bash
# Presentation launcher for the HiTide phone app.
#
#   npm run present              iOS Simulator on this Mac. Uses localhost, so it survives Wi-Fi changes.
#   npm run present -- --phone   Real phones with Expo Go on the same Wi-Fi (uses this Mac's LAN IP).
#   npm run present -- --sample  No backend at all: sample data only. Last-resort fallback.
#
# Options: --keep-replay  don't restart the July 4 replay (use when the dashboard demo is mid-run).
#
# It reuses a running backend on BACKEND_PORT (default 8000) if it is current; otherwise it starts one.
# It brings the replay to the Kerrville flood crest (about a minute at speed 1000), then starts Expo.
# Outreach is always mock here (PHOTON_MODE=mock): nobody is texted or called.
set -euo pipefail

MOBILE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$MOBILE/.." && pwd)"
PORT="${BACKEND_PORT:-8000}"
TARGET=sim
KEEP_REPLAY=0
CREST="2025-07-04T12:10"
REPLAY_SPEED=1000
LOG="${TMPDIR:-/tmp}/hitide-present-backend.log"

for arg in "$@"; do
  case "$arg" in
    --phone) TARGET=phone ;;
    --sample) TARGET=sample ;;
    --keep-replay) KEEP_REPLAY=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" || true; }

cd "$MOBILE"
[[ -d node_modules ]] || { say "Installing app dependencies"; npm install; }

if [[ "$TARGET" == "sample" ]]; then
  say "Sample-data mode: no backend. Every screen works; flood data is illustrative."
  unset EXPO_PUBLIC_API_URL EXPO_PUBLIC_USER_ID
  exec npx expo start --clear
fi

# ---- backend -------------------------------------------------------------------------------------
BACKEND_PID=""
# Stop the backend we started (uv and its uvicorn child), never one we reused.
cleanup() {
  [[ -n "$BACKEND_PID" ]] || return 0
  pkill -TERM -P "$BACKEND_PID" 2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  gauges=$(http_code "http://localhost:$PORT/api/region/gauges")
  dana=$(http_code "http://localhost:$PORT/api/users/hc-dana/danger")
  floodmap=$(http_code "http://localhost:$PORT/api/region/flood-layer?bbox=-99.18,29.99,-99.08,30.08")
  if [[ "$gauges" != "200" || "$dana" == "404" || "$floodmap" == "404" ]]; then
    die "A backend on :$PORT is out of date (gauges=$gauges, hc-dana=$dana, flood-layer=$floodmap). Stop it (lsof -nP -iTCP:$PORT) and rerun."
  fi
  say "Reusing the backend on :$PORT"
  if [[ "$TARGET" == "phone" ]] && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | grep -q '127.0.0.1'; then
    die "That backend only listens on localhost, so phones can't reach it. Restart it with --host 0.0.0.0."
  fi
else
  HOST=127.0.0.1
  [[ "$TARGET" == "phone" ]] && HOST=0.0.0.0
  say "Starting the backend on $HOST:$PORT (test data, mock outreach). Log: $LOG"
  (cd "$ROOT/backend" && DATA_MODE=test PHOTON_MODE=mock exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT") >"$LOG" 2>&1 &
  BACKEND_PID=$!
  for _ in $(seq 1 90); do [[ "$(http_code "http://localhost:$PORT/api/safety/summary")" == "200" ]] && break; sleep 1; done
  [[ "$(http_code "http://localhost:$PORT/api/safety/summary")" == "200" ]] || die "Backend didn't start. See $LOG"
fi

# ---- replay at the flood crest -------------------------------------------------------------------
sim_time() {
  curl -s --max-time 5 "http://localhost:$PORT/api/region/state" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sim_time") or "")' 2>/dev/null || true
}
now_sim="$(sim_time)"
if [[ "$KEEP_REPLAY" == "1" ]]; then
  say "Keeping the current replay (sim time: ${now_sim:-not started})"
elif [[ -n "$now_sim" && ! "$now_sim" < "$CREST" ]]; then
  say "Replay is already at the crest (sim time $now_sim)"
else
  say "Starting the July 4, 2025 replay at ${REPLAY_SPEED}x (this also restarts it on the dashboard)"
  curl -s -X POST --max-time 10 "http://localhost:$PORT/api/demo/start?scenario=hill_country&speed=$REPLAY_SPEED" >/dev/null
  for _ in $(seq 1 150); do
    now_sim="$(sim_time)"
    [[ -n "$now_sim" && ! "$now_sim" < "$CREST" ]] && break
    sleep 1
  done
  say "Replay sim time: ${now_sim:-unknown}"
fi

# ---- app -----------------------------------------------------------------------------------------
if [[ "$TARGET" == "phone" ]]; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  [[ -n "$IP" ]] || die "No Wi-Fi IP found. Use the simulator (npm run present) or --sample."
  export EXPO_PUBLIC_API_URL="http://$IP:$PORT"
  say "Phones: open Expo Go and scan the QR code (same Wi-Fi as this Mac). API: $EXPO_PUBLIC_API_URL"
  say "If venue Wi-Fi blocks phone-to-laptop traffic, use the simulator or --sample instead."
else
  export EXPO_PUBLIC_API_URL="http://localhost:$PORT"
  if ! xcrun simctl list devices booted | grep -q Booted; then
    DEVICE="$(xcrun simctl list devices available | grep -Eo 'iPhone[^(]*\(([0-9A-F-]{36})\)' | head -1 | grep -Eo '[0-9A-F-]{36}' || true)"
    if [[ -z "$DEVICE" ]]; then
      RUNTIME="$(xcrun simctl list runtimes | grep -Eo 'com\.apple\.CoreSimulator\.SimRuntime\.iOS-[0-9-]+' | tail -1)"
      [[ -n "$RUNTIME" ]] || die "No iOS simulator runtime. Install one in Xcode > Settings > Components, or use --phone/--sample."
      # Device types are listed newest first; the runtime only accepts recent models, so take the first that works.
      for TYPE in $(xcrun simctl list devicetypes | grep -Eo 'com\.apple\.CoreSimulator\.SimDeviceType\.iPhone-[0-9A-Za-z-]+'); do
        DEVICE="$(xcrun simctl create 'HiTide iPhone' "$TYPE" "$RUNTIME" 2>/dev/null || true)"
        [[ -n "$DEVICE" ]] && { say "Created an iPhone simulator (${TYPE##*.})"; break; }
      done
      [[ -n "$DEVICE" ]] || die "Couldn't create an iPhone simulator for $RUNTIME. Use --phone or --sample."
    fi
    say "Booting the simulator"
    xcrun simctl boot "$DEVICE" 2>/dev/null || true
  fi
  open -a Simulator
  say "Press i in Expo to open the app in the simulator (Expo installs Expo Go on first run)."
fi
export EXPO_PUBLIC_USER_ID=hc-dana
say "In the app: Profile > Developer (or long-press the HiTide mark) > Reset demo, then Start."
npx expo start --clear
