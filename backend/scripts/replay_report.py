"""Counterfactual report for the July 4, 2025 replay:  uv run python -m scripts.replay_report

For every critical point the replay truly floods (>= 6 in, the NWS "loss of control" depth):
  t_truth   first time the replay truth reaches 6 in
  t_drone   first wet drone snapshot (system with drones)
  t_gauges  first time a gauges-only system rates it likely/confirmed flooded (same fusion, no drones)
Plus: first community the system cuts off vs the real Flash Flood Emergency (04:04 CDT), and drone km
vs a naive nearest-neighbour patrol of every floodable point from the three stations.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from critical.loop import CriticalLoop
from drone.dispatch import distance_m
from fusion.segment_status import p_flooded, status
from sim.region import load_region
from sim.region_flood import RegionFlood, epoch

STEP_S = 60.0
LOSS_OF_CONTROL_IN = 6.0
CDT = timezone(timedelta(hours=-5))


def hm(t: float | None) -> str:
    return "never" if t is None else datetime.fromtimestamp(t, tz=CDT).strftime("%H:%M")


def naive_patrol_km(loop: CriticalLoop) -> float:
    pts = [(p["lon"], p["lat"]) for p in loop.points.values()]
    km = 0.0
    for st in loop.stations:  # each station sweeps its nearest third, nearest-neighbour order
        mine = [q for q in pts if min(loop.stations, key=lambda s: distance_m(q[1], q[0], s.lat, s.lon)) is st]
        pos = (st.lon, st.lat)
        while mine:
            nxt = min(mine, key=lambda q: distance_m(pos[1], pos[0], q[1], q[0]))
            km += distance_m(pos[1], pos[0], nxt[1], nxt[0]) / 1000
            pos = nxt
            mine.remove(nxt)
        km += distance_m(pos[1], pos[0], st.lat, st.lon) / 1000
    return km


def run(policy: str) -> tuple[CriticalLoop, dict, float | None, str]:
    region = load_region()
    flood = RegionFlood(region)
    loop = CriticalLoop(region, flood, policy=policy)
    replay = region.cfg["replay"]
    t, end = epoch(replay["start_local"]), epoch(replay["end_local"])
    first = {k: {} for k in ("truth", "drone", "gauges")}
    first_cut, first_cut_name = None, ""
    while t <= end:
        loop.step(t)
        truth = flood.truth_depth_in(t)
        for pid, p in loop.points.items():
            idx = [region.edge_index[e] for e in p["edge_ids"] if e in region.edge_index]
            if idx and float(truth[idx].max()) >= LOSS_OF_CONTROL_IN:
                first["truth"].setdefault(pid, t)
            o = loop.obs.get(pid)
            if o and o.water_on_road:
                first["drone"].setdefault(pid, o.t)
        gauges = flood.gauge_status(t)
        sig = loop._point_signals(t, flood.belief_depth_in(t), gauges, loop.frame)  # noqa: SLF001
        for pid, s in sig.items():
            if status(p_flooded(replace(s, drone=None))) in ("likely_flooded", "confirmed_flooded"):
                first["gauges"].setdefault(pid, t)
        if first_cut is None:
            cut = [n for n, st in loop.node_state.items() if st.status == "cut_off" and st.instruction == "shelter_in_place"]
            if cut:
                first_cut, first_cut_name = t, loop.nodes[cut[0]]["name"]
        t += STEP_S
    return loop, first, first_cut, first_cut_name


def chokepoint_stats(loop: CriticalLoop, first: dict) -> dict:
    """Flooded points that are some community's only way out, weighted by the households behind them."""
    hh: dict[str, int] = {}
    for n in loop.nodes.values():
        for u in n["unavoidable"]:
            hh[u] = hh.get(u, 0) + n["households"]
    flooded = [pid for pid in hh if pid in first["truth"]]
    known = [pid for pid in flooded if pid in first["drone"]]
    delays = sorted((first["drone"][pid] - first["truth"][pid]) / 60 for pid in known)
    return {"flooded_chokepoints": len(flooded), "households_behind_them": sum(hh[p] for p in flooded),
            "confirmed_by_drone": len(known), "households_confirmed": sum(hh[p] for p in known),
            "median_min_water_to_drone": delays[len(delays) // 2] if delays else None}


def main() -> int:
    patrol_loop, patrol_first, _, _ = run("patrol")
    loop, first, first_cut, first_cut_name = run("priority")
    region = loop.region
    replay = region.cfg["replay"]
    print("chokepoints, priority planner:", json.dumps(chokepoint_stats(loop, first)))
    print("chokepoints, naive patrol    :", json.dumps(chokepoint_stats(patrol_loop, patrol_first)),
          "drone_km", patrol_loop.counters()["drone_km"])
    flooded = sorted(first["truth"], key=lambda pid: first["truth"][pid])
    rows, lead_drone, lead_gauges = [], [], []
    for pid in flooded:
        tt, td, tg = first["truth"][pid], first["drone"].get(pid), first["gauges"].get(pid)
        rows.append({"point": pid, "name": loop.points[pid]["name"], "waterway": loop.points[pid]["waterway"],
                     "truth": hm(tt), "drone": hm(td), "gauges_only": hm(tg)})
        if td is not None:
            lead_drone.append((td - tt) / 60)
        if tg is not None:
            lead_gauges.append((tg - tt) / 60)
    ffe = epoch(replay["warnings"][1]["at"])
    summary = {
        "flooded_points": len(flooded),
        "known_by_drone": len(lead_drone), "known_by_gauges_only": len(lead_gauges),
        "median_min_after_truth_drone": sorted(lead_drone)[len(lead_drone) // 2] if lead_drone else None,
        "median_min_after_truth_gauges": sorted(lead_gauges)[len(lead_gauges) // 2] if lead_gauges else None,
        "first_cut_off": hm(first_cut), "first_cut_off_node": first_cut_name,
        "minutes_before_flash_flood_emergency": None if first_cut is None else round((ffe - first_cut) / 60),
        "drone_km": loop.counters()["drone_km"], "naive_patrol_km_one_pass": round(naive_patrol_km(loop), 1),
        "points_checked": loop.counters()["points_checked"], "floodable_points": len(loop.points),
    }
    print(json.dumps(summary, indent=1))
    for r in rows[:25]:
        print(f"  {r['truth']}  drone {r['drone']:>5}  gauges-only {r['gauges_only']:>5}  {r['name'][:34]} ({r['waterway']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
