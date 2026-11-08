# Opponent scouting

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The ScrabbleBot team, reviewing opponents before today's 10:45 submission deadline.

## Product Purpose

Scout the top leaderboard bots, launch any number of behavioral clones (Pegasus-vXXX) fitted to their public match history with held-out fidelity shown before launch, and manage every bot runner on this machine from one Fleet view.

## Capabilities and Constraints

Clone v2 models bids with a censored regression over rack/cash/clock/rival state and fits word-play style. It is validated against the source's latest matches and compared to the legacy median copy. Each clone has an independent credential, model snapshot, process, heartbeat, results log and controls (drain, stop, restart, logs). Ratings and ranks are pulled live from the leaderboard. Clones are behavioral estimates from public data, not source code. Private racks are sampled.
