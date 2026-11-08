"""Stress + accuracy simulation for the per-user danger pipeline (backend/safety/).

Replays July 4, 2025 (01:00-07:30 CDT) over thousands of simulated Kerr County users and scores what the system
believed against the replay's TRUTH depths (which the system never sees):

  recall      users whose road truly flooded (>= 6 in within 150 m) that we rated DANGER+ before the water came
  lead time   minutes between our first DANGER+ and the water arriving at them
  false alarm users rated DANGER+ whose surroundings never got even 3 in (truth, within 400 m)
  spam        messages per user (median / p95 / max) with sampled replies (60% safe, 10% help, 30% silent)
  latency     monitor refresh per step and per-ping assessment

Faults (--fault): usgs_dark (every gauge stops reporting at 04:00), nws_down (no alerts at all),
stale (every source marked stale), none. --load N: N moving users pinging every 10 s (latency only).

Run: cd backend && uv run python scripts/stress_safety.py --users 2000 --fault none
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import networkx as nx
import numpy as np

from app.config import DATA_DIR
from critical.loop import CriticalLoop
from observe.frame import SourceStatus
from safety.context import build_context
from safety.hazard import Locator
from safety.levels import Level
from safety.monitor import SafetyMonitor
from safety.motion import Ping
from safety.users import SafetyUser, UserRegistry
from scripts.gen_region_users import generate
from sim.region import load_region, to_xy
from sim.region_flood import RegionFlood, epoch

START, END = "2025-07-04T01:00:00-05:00", "2025-07-04T07:30:00-05:00"
TRUE_WET_IN, TRUE_DRY_IN = 6.0, 3.0
AT_YOU_M, AROUND_M = 150.0, 400.0
DRIVE_MPS = 13.0
OUT_DIR = DATA_DIR / "experiments"


# ---- faults ------------------------------------------------------------------
class FaultObservations:
    """Wrap the replay observations: drop alerts and/or mark sources degraded."""

    def __init__(self, inner: Any, fault: str):
        self.inner, self.fault, self.mode = inner, fault, inner.mode

    def frame_at(self, t: float):
        f = self.inner.frame_at(t)
        src = dict(f.sources)
        if self.fault == "nws_down":
            src["nws_alerts"] = SourceStatus("unavailable", "none", error="injected outage")
            return replace(f, alerts=(), sources=MappingProxyType(src))
        if self.fault == "stale":
            src = {k: SourceStatus("stale", v.provenance, v.as_of, detail="injected staleness") for k, v in src.items()}
            return replace(f, sources=MappingProxyType(src))
        return f

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def truncated_flood(region, cutoff: float) -> RegionFlood:
    path = DATA_DIR / "region" / region.id / "hydrographs_2025-07-04.json"
    hydro = json.loads(path.read_text())["gauges"]
    cut = {site: {**rec, "series": [[ts, v] for ts, v in rec["series"] if epoch(ts) <= cutoff]}
           for site, rec in hydro.items()}
    return RegionFlood(region, hydro=cut)


# ---- population ----------------------------------------------------------------
def population(n: int, region, loop: CriticalLoop, rng: random.Random) -> tuple[list[SafetyUser], dict[str, list]]:
    """30% at a crossing, 50% at home in populated areas, 20% driving a route. Returns users and driver paths."""
    base = generate(n)
    pts = list(loop.points.values())
    g = nx.Graph(region.graph.to_undirected(as_view=False))
    nodes = list(g.nodes)
    users, paths = [], {}
    for k, d in enumerate(base):
        lat, lon = d["home"]["lat"], d["home"]["lon"]
        role = "home"
        r = rng.random()
        if r < 0.30:
            p = rng.choice(pts)
            lat, lon = p["lat"] + rng.uniform(-3e-4, 3e-4), p["lon"] + rng.uniform(-3e-4, 3e-4)
            role = "crossing"
        elif r < 0.50:
            role = "driver"
        u = SafetyUser(d["id"], d["name"], d["age"], d["phone"], lat, lon, d["contact_name"], d["contact_phone"],
                       d.get("parent_phone"), d["profile"], True, (role,))
        users.append(u)
        if role == "driver":
            for _ in range(10):
                a, b = rng.sample(nodes, 2)
                try:
                    path = nx.shortest_path(g, a, b, weight="length")
                except nx.NetworkXNoPath:
                    continue
                if len(path) > 8:
                    paths[u.id] = [(g.nodes[x]["y"], g.nodes[x]["x"]) for x in path]
                    break
    return users, paths


def position_on(path: list[tuple[float, float]], dist_m: float) -> tuple[float, float, float]:
    """Point dist_m along a polyline (loops back and forth), with heading."""
    seg = [(a, b, float(np.hypot(*(to_xy(np.array([b[1]]), np.array([b[0]])) - to_xy(np.array([a[1]]), np.array([a[0]])))[0])))
           for a, b in zip(path, path[1:])]
    total = sum(s for *_, s in seg) or 1.0
    d = dist_m % (2 * total)
    fwd = d <= total
    d = d if fwd else 2 * total - d
    for a, b, s in seg:
        if d <= s or s == 0:
            w = 0 if s == 0 else d / s
            lat, lon = a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w
            src, dst = (a, b) if fwd else (b, a)
            hd = float(np.degrees(np.arctan2((dst[1] - src[1]) * np.cos(np.radians(lat)), dst[0] - src[0])) % 360)
            return lat, lon, hd
        d -= s
    return path[-1][0], path[-1][1], 0.0


# ---- fake outreach with sampled replies ----------------------------------------------
class SimOutreach:
    """Each user has a fixed persona: 60% answer SAFE, 10% ask for HELP, 30% never answer (asleep, no signal)."""

    def __init__(self, rng: random.Random):
        self.rng, self.sent, self.pending = rng, [], []
        self.now = 0.0
        self.persona: dict[str, str | None] = {}

    def _kind(self, uid: str) -> str | None:
        if uid not in self.persona:
            r = self.rng.random()
            self.persona[uid] = "safe" if r < 0.6 else ("need_help" if r < 0.7 else None)
        return self.persona[uid]

    async def send(self, msg) -> dict:
        self.sent.append((self.now, msg.driver_id, msg.recipient, msg.channel))
        kind = self._kind(msg.driver_id)
        if msg.recipient == "driver" and msg.channel in ("poll", "voice") and kind:
            self.pending.append((self.now + self.rng.uniform(120, 600), msg.driver_id, kind))
        return {"status": "sent"}


# ---- run -----------------------------------------------------------------------
def run(n_users: int, fault: str, step_s: float, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    region = load_region("hill_country")
    truth_flood = RegionFlood(region)
    belief_flood = truncated_flood(region, epoch("2025-07-04T04:00:00-05:00")) if fault == "usgs_dark" else truth_flood
    loop = CriticalLoop(region, belief_flood)
    if fault in ("nws_down", "stale"):
        loop.configure(FaultObservations(loop.observations, fault), True, belief_flood)
    loc = Locator(region, loop.points)
    users, paths = population(n_users, region, loop, rng)
    out = SimOutreach(rng)

    async def emit(*_a): return None

    mon = SafetyMonitor(loc, UserRegistry(users, registry_path=None), out, emit, state_path=None)
    t0, t1 = epoch(START), epoch(END)
    first_alert: dict[str, dict[int, float]] = {u.id: {} for u in users}
    first_wet: dict[str, float] = {}
    ever_dryish: dict[str, float] = {u.id: 0.0 for u in users}
    drove = {u.id: 0.0 for u in users}
    refresh_ms, ping_ms, step_ms = [], [], []
    conf = {"high": 0, "medium": 0, "low": 0}

    async def go() -> None:
        t = t0
        while t <= t1:
            s = time.perf_counter()
            loop.step(t)
            step_ms.append((time.perf_counter() - s) * 1000)
            mon.ctx = build_context(loop)
            out.now = t
            # drivers ping
            for uid, path in paths.items():
                drove[uid] += DRIVE_MPS * step_s
                lat, lon, hd = position_on(path, drove[uid])
                s = time.perf_counter()
                d = mon.ping(uid, Ping(lat, lon, t, DRIVE_MPS, hd, 10.0))
                ping_ms.append((time.perf_counter() - s) * 1000)
                await mon.dispatch([d])
            s = time.perf_counter()
            decisions = mon.refresh()
            refresh_ms.append((time.perf_counter() - s) * 1000)
            await mon.dispatch(decisions)
            # replies that have "arrived" by now
            due = [p for p in out.pending if p[0] <= t]
            out.pending = [p for p in out.pending if p[0] > t]
            for _, uid, kind in due:
                await mon.dispatch_actions(mon.users.get(uid), mon.reply(uid, kind, "driver"))
            # score against truth
            truth = truth_flood.truth_depth_in(t)
            for u in users:
                tr = mon.tracks.get(u.id)
                if tr is None or tr.last is None:
                    continue
                a = tr.last
                conf[a.confidence] += 1
                for lv in (Level.WARNING, Level.DANGER):
                    if a.level >= lv and int(lv) not in first_alert[u.id]:
                        first_alert[u.id][int(lv)] = t
                m = a.motion
                hood = loc.neighborhood(m.lat, m.lon)
                at = [i for i, dd in hood.near.items() if dd <= AT_YOU_M]
                around = list(hood.near)
                if at and float(truth[at].max()) >= TRUE_WET_IN and u.id not in first_wet:
                    first_wet[u.id] = t
                if around:
                    ever_dryish[u.id] = max(ever_dryish[u.id], float(truth[around].max()))
            t += step_s

    wall = time.perf_counter()
    asyncio.run(go())
    wall = time.perf_counter() - wall

    exposed = list(first_wet)
    def recall(lv: Level) -> tuple[float, list[float]]:
        hits, leads = 0, []
        for uid in exposed:
            ft = first_alert[uid].get(int(lv))
            if ft is not None and ft <= first_wet[uid]:
                hits += 1
                leads.append((first_wet[uid] - ft) / 60)
        return (hits / len(exposed) if exposed else float("nan")), leads

    rec_d, lead_d = recall(Level.DANGER)
    rec_w, lead_w = recall(Level.WARNING)
    flagged = [uid for uid, fa in first_alert.items() if int(Level.DANGER) in fa]
    false_alarm = [uid for uid in flagged if ever_dryish[uid] < TRUE_DRY_IN]
    per_user: dict[str, int] = {u.id: 0 for u in users}
    by_channel: dict[str, int] = {}
    for _, uid, who, ch in out.sent:
        per_user[uid] += 1
        by_channel[f"{who}:{ch}"] = by_channel.get(f"{who}:{ch}", 0) + 1
    counts = sorted(per_user.values())
    pct = lambda xs, q: (float(np.percentile(xs, q)) if xs else None)  # noqa: E731
    roles = {r: sum(1 for u in users if r in u.tags) for r in ("crossing", "home", "driver")}
    return {
        "fault": fault, "users": len(users), "roles": roles, "step_s": step_s, "seed": seed,
        "wall_s": round(wall, 1),
        "truth": {"exposed_users": len(exposed), "definition": f">= {TRUE_WET_IN} in within {AT_YOU_M:.0f} m (replay truth)"},
        "danger": {"recall": round(rec_d, 3), "lead_min_median": pct(lead_d, 50), "lead_min_p10": pct(lead_d, 10)},
        "warning": {"recall": round(rec_w, 3), "lead_min_median": pct(lead_w, 50), "lead_min_p10": pct(lead_w, 10)},
        "flagged_danger_users": len(flagged),
        "false_alarm": {"users": len(false_alarm), "share_of_flagged": round(len(false_alarm) / max(1, len(flagged)), 3),
                        "definition": f"DANGER+ but truth < {TRUE_DRY_IN} in within {AROUND_M:.0f} m all night"},
        "messages": {"total": len(out.sent), "per_user_median": pct(counts, 50), "per_user_p95": pct(counts, 95),
                     "per_user_max": max(counts) if counts else 0, "by_recipient_channel": by_channel},
        "final_levels": mon.counts(),
        "confidence_samples": conf,
        "latency_ms": {"refresh_median": pct(refresh_ms, 50), "refresh_p99": pct(refresh_ms, 99),
                       "ping_median": pct(ping_ms, 50), "ping_p99": pct(ping_ms, 99),
                       "loop_step_median": pct(step_ms, 50)},
    }


def load_test(n: int, seconds: float, seed: int) -> dict[str, Any]:
    """n users at random spots in the region, all moving, pinging every 10 s; latency of ping + refresh."""
    rng = random.Random(seed)
    region = load_region("hill_country")
    loop = CriticalLoop(region, RegionFlood(region))
    loop.step(epoch("2025-07-04T04:30:00-05:00"))
    loc = Locator(region, loop.points)
    bb = region.cfg["bbox"]
    base = generate(min(n, 5000))
    users = []
    for k in range(n):
        d = base[k % len(base)]
        users.append(SafetyUser(f"load-{k}", d["name"], d["age"], f"sim:load-{k}",
                                rng.uniform(bb["south"], bb["north"]), rng.uniform(bb["west"], bb["east"]),
                                profile=d["profile"]))

    class Null:
        async def send(self, msg):
            return {"status": "sent"}

    async def emit(*_a): return None

    mon = SafetyMonitor(loc, UserRegistry(users, registry_path=None), Null(), emit, state_path=None)
    mon.ctx = build_context(loop)
    pos = {u.id: (u.home_lat, u.home_lon, rng.uniform(0, 360)) for u in users}
    ping_ms, refresh_ms = [], []
    t = mon.ctx.t
    for _ in range(int(seconds / 10)):
        t += 10
        for u in users:
            lat, lon, hd = pos[u.id]
            lat += 130 / 111_000 * np.cos(np.radians(hd))
            lon += 130 / (111_000 * np.cos(np.radians(lat))) * np.sin(np.radians(hd))
            pos[u.id] = (lat, lon, hd)
            s = time.perf_counter()
            mon.ping(u.id, Ping(lat, lon, t, 13.0, hd, 10.0))
            ping_ms.append((time.perf_counter() - s) * 1000)
        s = time.perf_counter()
        mon.refresh()
        refresh_ms.append((time.perf_counter() - s) * 1000)
    return {"load_users": n, "pings": len(ping_ms),
            "ping_ms": {"median": float(np.median(ping_ms)), "p99": float(np.percentile(ping_ms, 99))},
            "pings_per_s_single_thread": round(1000 / float(np.mean(ping_ms))),
            "refresh_ms": {"median": float(np.median(refresh_ms)), "max": float(max(refresh_ms))}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=2000)
    ap.add_argument("--fault", default="none", choices=["none", "usgs_dark", "nws_down", "stale"])
    ap.add_argument("--step", type=float, default=120.0, help="sim seconds per loop step")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--load", type=int, default=0, help="run the latency load test with this many users instead")
    ap.add_argument("--load-seconds", type=float, default=600.0)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.load:
        res = load_test(args.load, args.load_seconds, args.seed)
        name = f"safety_load_{args.load}.json"
    else:
        res = run(args.users, args.fault, args.step, args.seed)
        name = f"safety_stress_{args.fault}_{args.users}.json"
    (OUT_DIR / name).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    print(f"wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
