#!/bin/zsh
# Tournament launcher for larper (bot 323): one runner, compiled JS, Mac kept awake.
# Usage (from anywhere): ./bot-starter/run-larper.sh
# Strategy is unchanged: STRATEGY=forge.
set -e
cd "$(dirname "$0")"

# Never run two copies of the same bot: stop any existing larper runner first.
OLD=""
for p in $(pgrep -f "index"); do
  if ps eww "$p" 2>/dev/null | tr ' ' '\n' | grep -qx "BOT_NAME=larper"; then OLD="$OLD $p"; fi
done
if [ -n "${OLD// }" ]; then
  echo "Stopping old larper runner(s):$OLD"
  kill $OLD 2>/dev/null || true
  sleep 2
fi

mkdir -p bench/results/larper
echo "Starting larper (forge, tournament 3). Ctrl+C to stop."
# caffeinate -i keeps the Mac from idle-sleeping while the bot runs.
# Runs under tsx: compiled dist/ fails (generated bindings use extensionless imports).
BOT_NAME=larper STRATEGY=forge TOURNAMENT_ID=3 QUIET=1 \
SCOUT_RUNTIME_PATH="$PWD/bench/results/larper/runtime.json" \
caffeinate -i node --import tsx src/index.ts 2>&1 | tee -a bench/results/larper/bot.log
