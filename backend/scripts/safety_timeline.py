"""July 4, 2025 replay through the per-user danger pipeline -> data/experiments/safety_timeline.json (for slides).

Per step: users at each level (belief), users truly near deep water (replay truth), messages sent so far, and the
demo personas' level + top reason. Mock outreach, no network.
Run: cd backend && uv run python scripts/safety_timeline.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.config import DATA_DIR
from critical.loop import CriticalLoop
from safety.context import build_context
from safety.hazard import Locator
from safety.levels import Level
from safety.monitor import SafetyMonitor
from safety.users import UserRegistry
from sim.region import load_region
from sim.region_flood import RegionFlood, epoch

STEP_S = 300.0
WET_IN, NEAR_M = 6.0, 150.0
PERSONAS = ("hc-ruth", "hc-marco", "hc-jess")
CDT = timezone(timedelta(hours=-5))


class CountingOutreach:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, msg) -> dict:
        self.sent.append({"user": msg.driver_id, "recipient": msg.recipient, "channel": msg.channel})
        return {"status": "sent"}


async def main() -> None:
    region = load_region("hill_country")
    flood = RegionFlood(region)
    loop = CriticalLoop(region, flood)
    loc = Locator(region, loop.points)
    out = CountingOutreach()

    async def emit(*_a): return None

    mon = SafetyMonitor(loc, UserRegistry.load(registry=None), out, emit, state_path=None)
    users = mon.users.all()
    rows, persona_rows = [], {p: [] for p in PERSONAS}
    t, end = epoch("2025-07-04T01:00:00-05:00"), epoch("2025-07-04T07:30:00-05:00")
    while t <= end:
        loop.step(t)
        await mon.after_step(loop)
        truth = flood.truth_depth_in(t)
        wet = 0
        for u in users:
            near = [i for i, d in loc.neighborhood(u.home_lat, u.home_lon).near.items() if d <= NEAR_M]
            wet += bool(near) and float(truth[near].max()) >= WET_IN
        counts = mon.counts()
        clock = datetime.fromtimestamp(t, tz=CDT).strftime("%H:%M")
        rows.append({"t": clock, **counts, "truly_near_deep_water": wet, "messages_sent": len(out.sent),
                     "alerts": [a.get("event") for a in loop.alerts]})
        for p in PERSONAS:
            a = mon.tracks[p].last if p in mon.tracks else None
            if a is not None:
                persona_rows[p].append({"t": clock, "level": a.level.label, "reason": a.reasons[0] if a.reasons else ""})
        t += STEP_S
    timelines = {p: [{"t": t_, "what": w} for t_, w in
                     ((datetime.fromtimestamp(x, tz=CDT).strftime("%H:%M"), y) for x, y in mon.tracks[p].response.timeline)]
                 for p in PERSONAS if p in mon.tracks}
    by = {}
    for s in out.sent:
        k = f"{s['recipient']}:{s['channel']}"
        by[k] = by.get(k, 0) + 1
    res = {"users": len(users), "step_s": STEP_S, "rows": rows, "personas": persona_rows, "ladders": timelines,
           "messages_by_recipient_channel": by,
           "levels": [lv.label for lv in Level]}
    path = DATA_DIR / "experiments" / "safety_timeline.json"
    path.write_text(json.dumps(res, indent=1))
    print(f"wrote {path}: {len(rows)} steps, {len(out.sent)} messages")


if __name__ == "__main__":
    asyncio.run(main())
