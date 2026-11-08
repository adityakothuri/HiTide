"""Digest of the July 4, 2025 replay (per-minute p / status / node states / counters / events).

Regenerate only when a change is *meant* to alter replay behaviour:
    uv run python -m tests.golden_replay > tests/fixtures/replay_golden.json
"""

from __future__ import annotations

import hashlib
import json

from critical.loop import CriticalLoop
from sim.region import load_region
from sim.region_flood import RegionFlood, epoch

STEP_S = 60.0


def replay_digest(policy: str = "priority") -> dict:
    region = load_region("hill_country")
    loop = CriticalLoop(region, RegionFlood(region), policy=policy)
    rp = region.cfg["replay"]
    t, end = epoch(rp["start_local"]), epoch(rp["end_local"])
    steps = []
    while t <= end:
        events = loop.step(t)
        kinds = sorted({k for k, _ in events} - {"drones.update"})
        alerts = [p.get("event") for k, p in events if k == "region.alert"]
        state = {"p": loop.p, "status": loop.status,
                 "nodes": {n: [s.status, s.instruction, s.rescue] for n, s in loop.node_state.items()},
                 "counters": loop.counters(), "kinds": kinds, "alerts": alerts}
        steps.append(hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16])
        t += STEP_S
    return {"policy": policy, "steps": steps, "final_counters": loop.counters()}


if __name__ == "__main__":
    print(json.dumps({p: replay_digest(p) for p in ("priority", "patrol")}, indent=1))
