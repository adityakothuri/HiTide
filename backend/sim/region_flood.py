"""Region-wide replay of the July 4, 2025 flood: TRUTH depths for the sim, BELIEF signals for fusion.

TRUTH  real gauges (the dead Hunt gauge continued from a downstream donor) + modeled ungauged creeks.
BELIEF only gauge readings that exist at time t. Ungauged creeks and dead gauges are unknown, so
       p_flooded stays near its prior there, and that's where drone snapshots carry the most information.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from sim.hand_flood import (
    LOW_WATER_FREEBOARD_M,
    MAX_GAP_S,
    Gauge,
    crossing_depth_in,
    fill_gap,
    interp_rise_vec,
)
from sim.flood import M_TO_IN
from sim.region import Region

PRE_EVENT_END = datetime.fromisoformat("2025-07-04T05:00:00+00:00").timestamp()  # midnight CDT
CELERITY_BOUNDS = (1.5, 6.0)


def epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


@dataclass(frozen=True)
class GaugeInfo:
    site: str
    name: str
    chain: str
    lon: float
    lat: float


def _gauge(site: str, rec: dict, s_m: float) -> Gauge:
    times = np.array([epoch(t) for t, _ in rec["series"]])
    stage = np.array([v for _, v in rec["series"]], dtype=float)
    pre = stage[times < PRE_EVENT_END]
    base = float(pre.min()) if pre.size else float(stage.min())
    return Gauge(site, s_m, times, stage, base)


def _fit_celerity(gauges: list[Gauge]) -> float:
    """Flood-wave speed from peak-time differences along the main stem (least squares through the origin)."""
    ordered = sorted(gauges, key=lambda g: g.s_m)
    ds, dt = [], []
    for a, b in zip(ordered, ordered[1:]):
        ta, tb = a.times[int(np.argmax(a.stage_ft))], b.times[int(np.argmax(b.stage_ft))]
        if tb > ta:
            ds.append(b.s_m - a.s_m)
            dt.append(tb - ta)
    if not ds:
        return 3.0
    c = float(np.dot(ds, dt) / np.dot(dt, dt))
    return float(np.clip(c, *CELERITY_BOUNDS))


class RegionFlood:
    def __init__(self, region: Region, hydro: dict | None = None):
        self.region = region
        cfg = region.cfg
        if hydro is None:
            path = region_path(region) / "hydrographs_2025-07-04.json"
            hydro = json.loads(path.read_text())["gauges"]
        self.info: dict[str, GaugeInfo] = {}
        belief: dict[str, list[Gauge]] = {}
        for g in cfg["gauges"]:
            rec = hydro[g["site"]]
            chain = region.chains[g["waterway"]]
            s_m = float(chain.s_m[chain.nearest(rec["lon"], rec["lat"])])
            belief.setdefault(g["waterway"], []).append(_gauge(g["site"], rec, s_m))
            self.info[g["site"]] = GaugeInfo(g["site"], g["name"], g["waterway"], rec["lon"], rec["lat"])
        self.belief_gauges = belief
        self.celerity = _fit_celerity(belief.get("Guadalupe River", []))
        self.truth_gauges = self._fill_dead(belief, cfg.get("gap_fill", {}))
        self._by_site = {g.site: g for gs in self.truth_gauges.values() for g in gs}

    def _fill_dead(self, belief: dict[str, list[Gauge]], gap_fill: dict[str, str]) -> dict[str, list[Gauge]]:
        by_site = {g.site: g for gs in belief.values() for g in gs}
        end = max(float(g.times[-1]) for g in by_site.values())
        truth = {}
        for chain, gs in belief.items():
            out = []
            for g in gs:
                donor = by_site.get(gap_fill.get(g.site, ""))
                if donor is not None:
                    g = fill_gap(g, donor, lag_s=(donor.s_m - g.s_m) / self.celerity, until_s=end)
                out.append(g)
            truth[chain] = out
        return truth

    # ---- rises per waterway sample -----------------------------------
    def _ungauged_rise(self, name: str, t: float) -> float:
        spec = self.region.cfg["ungauged"][name]
        r = self._by_site[spec["donor"]].rise_m(t + spec["lead_s"])
        return 0.0 if r is None else spec["scale"] * r

    def chain_rise(self, name: str, t: float, belief: bool) -> np.ndarray:
        chain = self.region.chains[name]
        gauges = (self.belief_gauges if belief else self.truth_gauges).get(name)
        if gauges:
            return interp_rise_vec(gauges, chain.s_m, t, self.celerity)
        if belief or name not in self.region.cfg.get("ungauged", {}):
            return np.full(chain.s_m.shape, np.nan)
        return np.full(chain.s_m.shape, self._ungauged_rise(name, t))

    def minor_rise(self, t: float) -> float:
        spec = self.region.cfg["minor_streams"]
        r = self._by_site[spec["donor"]].rise_m(t + spec["lead_s"])
        return 0.0 if r is None else spec["scale"] * r

    # ---- per-segment outputs -----------------------------------------
    def _depths(self, t: float, belief: bool) -> np.ndarray:
        r = self.region
        depth = np.zeros(len(r.edge_ids))
        for ref in r.refs:
            rise = self.chain_rise(ref.chain, t, belief)[ref.sample_idx]
            z_ref = r.chains[ref.chain].z_ref_m[ref.sample_idx]
            # A road can't sit below normal flow: DEM samples where a road touches the water are fords.
            road = np.maximum(r.elev_m[ref.seg_idx], z_ref + LOW_WATER_FREEBOARD_M)
            d = np.nan_to_num(np.maximum(0.0, z_ref + rise - road), nan=0.0) * M_TO_IN
            np.maximum.at(depth, ref.seg_idx, d)
        return depth

    def truth_depth_in(self, t: float) -> np.ndarray:
        depth = self._depths(t, belief=False)
        rise = self.minor_rise(t)
        for eid, bridge in self.region.minor_crossings.items():
            i = self.region.edge_index[eid]
            depth[i] = max(depth[i], crossing_depth_in(rise, bridge))
        return depth

    def belief_depth_in(self, t: float) -> np.ndarray:
        """Gauges only: what the system can infer without eyes on the road."""
        return self._depths(t, belief=True)

    def gauge_status(self, t: float) -> list[dict]:
        out = []
        for gs in self.belief_gauges.values():
            for g in gs:
                info = self.info[g.site]
                past = g.times <= t
                online = bool(past.any()) and (t - float(g.times[past][-1])) <= MAX_GAP_S
                last_t = float(g.times[past][-1]) if past.any() else None
                last = float(g.stage_ft[past][-1]) if past.any() else None
                hour = g.times[past & (g.times >= t - 3600)]
                rate = None
                if online and hour.size >= 2:
                    k = np.nonzero(past & (g.times >= t - 3600))[0]
                    rate = float((g.stage_ft[k[-1]] - g.stage_ft[k[0]]) / max(1.0, (g.times[k[-1]] - g.times[k[0]]) / 3600))
                out.append({"site": g.site, "name": info.name, "waterway": info.chain, "lon": info.lon, "lat": info.lat,
                            "online": online, "stage_ft": last, "observed_at": last_t,
                            "rate_ft_per_hr": None if rate is None else round(rate, 2)})
        return out


def region_path(region: Region):
    from app.config import DATA_DIR
    return DATA_DIR / "region" / region.id
