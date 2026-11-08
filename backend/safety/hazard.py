"""Where is the user, and what is the water doing there?

`Locator` is built once per region (KD-trees over densified road geometry and critical points, height above
water per segment). `assess(locator, ctx, lat, lon, ...)` turns one position into a `LocationHazard`, and
`classify_hazard` maps that to a Level using only evidence (no profile). Missing evidence lowers confidence;
it never reads as "dry". Outside the modeled region only NWS alerts apply, and the level is capped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
from scipy.spatial import cKDTree

from app.config import safety_settings
from observe.alerts import Alert
from population.nodes import segment_hand
from safety.context import CATEGORY_RANK, SafetyContext
from safety.levels import Level
from sim.region import Region, to_xy

WET_STATUSES = ("likely_flooded", "confirmed_flooded")


@dataclass(frozen=True)
class NearbyPoint:
    id: str
    name: str
    kind: str
    waterway: str
    status: str
    p: float
    distance_m: float
    on_my_road: bool

    def public(self) -> dict[str, Any]:
        return {**self.__dict__, "distance_m": round(self.distance_m)}


@dataclass(frozen=True)
class LocationHazard:
    lat: float
    lon: float
    coverage: str                         # region | alerts_only
    edge_id: str | None = None            # nearest road within snap.on_road_m
    road_name: str | None = None
    distance_to_road_m: float | None = None
    waterway: str | None = None           # nearest named waterway governing this road
    height_above_water_m: float | None = None
    depth_in: float | None = None         # belief depth on the user's road; None = unknown
    max_depth_nearby_in: float | None = None
    unknown_nearby: bool = False          # some road within nearby_m has no gauge coverage
    worst_point: NearbyPoint | None = None
    in_warning: bool = False
    in_emergency: bool = False
    emergency_polygon: bool = False       # storm-based polygon (precise) vs. zone/area-wide
    in_watch: bool = False
    far_from_water: bool = False          # no modeled waterway in reach and no unnamed-stream crossing nearby
    alert_headlines: tuple[str, ...] = ()
    rain_in_hr: float | None = None
    gauge_rising: bool = False
    gauge_category: str | None = None
    forecast_category: str | None = None
    closure_nearby: str | None = None
    degraded_sources: tuple[str, ...] = ()
    ahead: tuple["AheadHit", ...] = ()    # while driving: worst hazards in the heading cone
    route: tuple["AheadHit", ...] = ()    # planned route: segments with water

    @property
    def confidence(self) -> str:
        if self.coverage != "region":
            return "low"
        if self.degraded_sources and (self.depth_in is None or "usgs_gage" in self.degraded_sources):
            return "low"
        if self.depth_in is None or self.unknown_nearby or self.degraded_sources:
            return "medium"
        return "high"

    def public(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("worst_point", "ahead", "route")}
        d["worst_point"] = self.worst_point.public() if self.worst_point else None
        d["ahead"] = [a.public() for a in self.ahead]
        d["route"] = [a.public() for a in self.route]
        d["confidence"] = self.confidence
        for k in ("distance_to_road_m", "height_above_water_m", "depth_in", "max_depth_nearby_in", "rain_in_hr"):
            if d[k] is not None:
                d[k] = round(float(d[k]), 1)
        return d


@dataclass(frozen=True)
class AheadHit:
    edge_id: str
    road_name: str
    distance_m: float
    depth_in: float | None
    point_status: str | None

    def public(self) -> dict[str, Any]:
        return {**self.__dict__, "distance_m": round(self.distance_m),
                "depth_in": None if self.depth_in is None else round(self.depth_in, 1)}


def _densify(coords: list[list[float]], step_m: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        xy = to_xy(np.array([x0, x1]), np.array([y0, y1]))
        n = max(1, int(math.ceil(float(np.hypot(*(xy[1] - xy[0]))) / step_m)))
        out.extend((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n))
    out.append(tuple(coords[-1]))  # type: ignore[arg-type]
    return out


@dataclass
class Locator:
    """Spatial index for one region. Immutable after construction; safe to share across threads."""
    region: Region
    points: Mapping[str, dict]
    cfg: Mapping[str, Any] = field(default_factory=safety_settings)

    def __post_init__(self) -> None:
        feats = self.region.segments_fc["features"]
        step = float(self.cfg["snap"]["densify_m"])
        lon, lat, owner = [], [], []
        for i, f in enumerate(feats):
            for x, y in _densify(f["geometry"]["coordinates"], step):
                lon.append(x)
                lat.append(y)
                owner.append(i)
        self.vertex_lonlat = np.column_stack([lon, lat])
        self.vertex_edge = np.array(owner, dtype=np.int64)
        self.tree = cKDTree(to_xy(np.array(lon), np.array(lat)))
        self.names = [f["properties"].get("name") or "Unnamed road" for f in feats]
        hand, _dist, ww = segment_hand(self.region)
        self.hand = hand
        self.waterway = ww
        self.point_ids = list(self.points)
        if self.point_ids:
            plon = np.array([self.points[p]["lon"] for p in self.point_ids])
            plat = np.array([self.points[p]["lat"] for p in self.point_ids])
            self.point_tree: cKDTree | None = cKDTree(to_xy(plon, plat))
        else:
            self.point_tree = None
        self.point_edges = {pid: frozenset(self.region.edge_index[e] for e in p["edge_ids"] if e in self.region.edge_index)
                            for pid, p in self.points.items()}
        self.minor_idx = frozenset(self.region.edge_index[e] for e in self.region.minor_crossings)
        bb = self.region.cfg["bbox"]
        self.bbox = (bb["west"], bb["south"], bb["east"], bb["north"])

    # ---- geometry --------------------------------------------------------
    def in_region(self, lat: float, lon: float) -> bool:
        w, s, e, n = self.bbox
        return w <= lon <= e and s <= lat <= n

    def xy(self, lat: float, lon: float) -> np.ndarray:
        return to_xy(np.array([lon]), np.array([lat]))[0]

    def nearest_edge(self, lat: float, lon: float) -> tuple[int, float]:
        d, k = self.tree.query(self.xy(lat, lon))
        return int(self.vertex_edge[k]), float(d)

    def _within(self, lat: float, lon: float, radius_m: float) -> dict[int, tuple[float, int]]:
        """Edge index -> (nearest distance m, nearest densified vertex) for every road within radius_m."""
        p = self.xy(lat, lon)
        idx = self.tree.query_ball_point(p, radius_m)
        out: dict[int, tuple[float, int]] = {}
        if not idx:
            return out
        d = np.hypot(*(self.tree.data[idx] - p).T)
        for k, dist in zip(idx, d):
            e = int(self.vertex_edge[k])
            if e not in out or dist < out[e][0]:
                out[e] = (float(dist), int(k))
        return out

    def edges_within(self, lat: float, lon: float, radius_m: float) -> dict[int, float]:
        """Edge index -> nearest distance (m) for every road within radius_m."""
        return {e: d for e, (d, _k) in self._within(lat, lon, radius_m).items()}

    def points_within(self, lat: float, lon: float, radius_m: float) -> list[tuple[str, float]]:
        if self.point_tree is None:
            return []
        p = self.xy(lat, lon)
        idx = self.point_tree.query_ball_point(p, radius_m)
        return sorted(((self.point_ids[k], float(np.hypot(*(self.point_tree.data[k] - p)))) for k in idx),
                      key=lambda x: x[1])

    def nearest_point(self, lat: float, lon: float, radius_m: float) -> tuple[str, float] | None:
        if self.point_tree is None:
            return None
        d, k = self.point_tree.query(self.xy(lat, lon))
        return (self.point_ids[int(k)], float(d)) if d <= radius_m else None

    def edges_ahead(self, lat: float, lon: float, heading_deg: float) -> dict[int, float]:
        """Roads within lookahead.distance_m inside the heading cone (bearing clockwise from north)."""
        la = self.cfg["lookahead"]
        p = self.xy(lat, lon)
        out: dict[int, float] = {}
        for e, (dist, k) in self._within(lat, lon, float(la["distance_m"])).items():
            if dist < 1.0:
                continue
            v = self.tree.data[k] - p
            bearing = math.degrees(math.atan2(v[0], v[1])) % 360.0
            if abs((bearing - heading_deg + 180.0) % 360.0 - 180.0) <= float(la["cone_deg"]):
                out[e] = dist
        return out

    def snap_route(self, coords: list[tuple[float, float]]) -> tuple[int, ...]:
        """Polyline (lat, lon) -> ordered unique edge indexes it passes over (densified, within on_road_m)."""
        on_road = float(self.cfg["snap"]["on_road_m"])
        seq: list[int] = []
        lonlat = [[lon, lat] for lat, lon in coords]
        for lon, lat in (_densify(lonlat, float(self.cfg["snap"]["densify_m"])) if len(lonlat) > 1 else lonlat):
            e, d = self.nearest_edge(lat, lon)
            if d <= on_road and (not seq or seq[-1] != e):
                seq.append(e)
        return tuple(dict.fromkeys(seq))


# ---- assessment -----------------------------------------------------------
def _alerts_at(alerts: tuple[Alert, ...], lat: float, lon: float, zones: frozenset[str], in_region: bool) -> list[Alert]:
    """Polygon alerts by point-in-polygon. Zone-only alerts (no polygon) are matched to the region's own zones, so
    they only count for users inside the region: a Kerr County zone says nothing about a point in Bexar County."""
    return [a for a in alerts if (a.geometry is not None or in_region) and a.covers(lon, lat, zones)]


def _depth(ctx: SafetyContext, i: int) -> float | None:
    return float(ctx.belief_in[i]) if bool(ctx.known[i]) else None


def _point_hit(loc: Locator, ctx: SafetyContext, pid: str, dist: float, my_edge: int | None) -> NearbyPoint:
    p = loc.points[pid]
    return NearbyPoint(pid, p.get("name", pid), p.get("kind", ""), p.get("waterway", ""),
                       ctx.point_status.get(pid, "open"), float(ctx.point_p.get(pid, 0.0)), dist,
                       my_edge is not None and my_edge in loc.point_edges.get(pid, frozenset()))


def _worst_point(hits: list[NearbyPoint]) -> NearbyPoint | None:
    order = {"confirmed_flooded": 3, "likely_flooded": 2, "unknown": 1, "open": 0}
    if not hits:
        return None
    return max(hits, key=lambda h: (order.get(h.status, 0), h.on_my_road, -h.distance_m))


def _edge_hits(loc: Locator, ctx: SafetyContext, edges: Mapping[int, float], min_depth: float) -> tuple[AheadHit, ...]:
    point_of_edge = {e: pid for pid, es in loc.point_edges.items() for e in es}
    hits = []
    for e, dist in edges.items():
        d = _depth(ctx, e)
        ps = ctx.point_status.get(point_of_edge.get(e, ""), None)
        if (d is not None and d >= min_depth) or ps in WET_STATUSES:
            hits.append(AheadHit(loc.region.edge_ids[e], loc.names[e], dist, d, ps))
    return tuple(sorted(hits, key=lambda h: h.distance_m)[:5])


def assess(loc: Locator, ctx: SafetyContext, lat: float, lon: float, heading_deg: float | None = None,
           driving: bool = False, route_edges: tuple[int, ...] = ()) -> LocationHazard:
    cfg = loc.cfg
    inside = loc.in_region(lat, lon)
    alerts = _alerts_at(ctx.alerts, lat, lon, ctx.region_zones, inside)
    alert_part = dict(
        in_warning=any(a.is_warning for a in alerts),
        in_emergency=any(a.is_warning and a.emergency for a in alerts),
        emergency_polygon=any(a.is_warning and a.emergency and a.geometry is not None for a in alerts),
        in_watch=any(a.level in ("watch", "advisory") for a in alerts),
        alert_headlines=tuple(dict.fromkeys(a.headline or a.event for a in alerts))[:3],
        degraded_sources=ctx.degraded_sources(),
    )
    if not inside or not ctx.ready:
        return LocationHazard(lat, lon, "alerts_only", **alert_part)

    snap = cfg["snap"]
    caution = float(cfg["depth_in"]["caution"])
    e, dist = loc.nearest_edge(lat, lon)
    on_road = dist <= float(snap["on_road_m"])
    my_edge = e if on_road else None
    near = loc.edges_within(lat, lon, float(snap["nearby_m"]))
    depths = [d for i in near if (d := _depth(ctx, i)) is not None]
    hits = [_point_hit(loc, ctx, pid, d, my_edge) for pid, d in loc.points_within(lat, lon, float(snap["nearby_m"]))]
    ww = loc.waterway[e] or None
    rain_pt = loc.nearest_point(lat, lon, float(snap["rain_point_m"]))
    closure = next((ctx.closures[pid] for pid, _ in loc.points_within(lat, lon, float(snap["closure_m"]))
                    if pid in ctx.closures), None)
    hand = float(loc.hand[e])
    far = not math.isfinite(hand) and not any(i in loc.minor_idx for i in near)
    ahead: tuple[AheadHit, ...] = ()
    if driving and heading_deg is not None:
        ahead = _edge_hits(loc, ctx, loc.edges_ahead(lat, lon, heading_deg), caution)
    route = _edge_hits(loc, ctx, {i: 0.0 for i in route_edges}, caution) if route_edges else ()
    return LocationHazard(
        lat, lon, "region",
        edge_id=loc.region.edge_ids[e] if on_road else None,
        road_name=loc.names[e] if on_road else None,
        distance_to_road_m=dist, waterway=ww,
        height_above_water_m=None if not math.isfinite(hand) else max(0.0, hand),
        depth_in=_depth(ctx, e) if on_road else None,
        max_depth_nearby_in=max(depths) if depths else None,
        unknown_nearby=any(not bool(ctx.known[i]) for i in near),
        worst_point=_worst_point(hits),
        rain_in_hr=ctx.rain_in_hr.get(rain_pt[0]) if rain_pt else None,
        gauge_rising=bool(ww and ww in ctx.rising_waterways),
        gauge_category=ctx.gauge_category.get(ww) if ww else None,
        forecast_category=ctx.forecast_category.get(ww) if ww else None,
        closure_nearby=closure, ahead=ahead, route=route, far_from_water=far,
        **alert_part,
    )


# ---- evidence -> level ----------------------------------------------------
# Kinds: what a reason is about. High ground at home softens "alert" and "nearby" reasons only.
ALERT, AT_YOU, NEARBY, AHEAD = "alert", "at_you", "nearby", "ahead"


def _findings(h: LocationHazard, stall_depth_in: float, cfg: Mapping[str, Any]) -> list[tuple[Level, str, str]]:
    caution, danger = float(cfg["depth_in"]["caution"]), float(cfg["depth_in"]["danger"])
    rain_heavy = (h.rain_in_hr or 0.0) >= float(cfg.get("heavy_rain_in_hr", 1.0))
    out: list[tuple[Level, str, str]] = []
    low_ground = h.height_above_water_m is not None and h.height_above_water_m < float(cfg["low_ground_m"])
    if h.in_emergency and (h.emergency_polygon or low_ground):
        out.append((Level.DANGER, "Flash Flood Emergency covers your location", ALERT))
    elif h.in_emergency:
        out.append((Level.WARNING, "Flash Flood Emergency declared for your area", ALERT))
    if h.in_warning:
        out.append((Level.WARNING, "Flash Flood Warning covers your location", ALERT))
    if h.in_watch:
        out.append((Level.WATCH, "Flood watch for your area", ALERT))
    if h.coverage != "region":
        return out
    road = h.road_name or "your road"
    d = h.depth_in
    if d is not None and d >= stall_depth_in:
        out.append((Level.CRITICAL, f"About {d:.0f} in of water on {road}: enough to stall your vehicle", AT_YOU))
    elif d is not None and d >= danger:
        out.append((Level.DANGER, f"About {d:.0f} in of water on {road}", AT_YOU))
    elif d is not None and d >= caution:
        out.append((Level.WARNING, f"Water on {road} (about {d:.0f} in)", AT_YOU))
    wp = h.worst_point
    if wp and wp.status == "confirmed_flooded" and wp.on_my_road and wp.distance_m <= float(cfg["snap"]["crossing_on_m"]):
        out.append((Level.CRITICAL, f"{wp.name} over {wp.waterway} is confirmed flooded where you are", AT_YOU))
    elif wp and wp.status in WET_STATUSES:
        out.append((Level.DANGER, f"{wp.name} over {wp.waterway} is {wp.status.replace('_', ' ')} "
                                  f"{wp.distance_m:.0f} m away", NEARBY))
    elif wp and wp.status == "unknown" and h.in_emergency:
        out.append((Level.DANGER, f"{wp.name} over {wp.waterway} ({wp.distance_m:.0f} m away) can't be checked "
                                  "and a Flash Flood Emergency is in effect", NEARBY))
    elif wp and wp.status == "unknown" and h.in_warning:
        out.append((Level.WARNING, f"{wp.name} over {wp.waterway} ({wp.distance_m:.0f} m away) can't be checked yet",
                    NEARBY))
    m = h.max_depth_nearby_in
    if m is not None and m >= danger:
        out.append((Level.DANGER if m >= stall_depth_in else Level.WARNING, f"Water up to {m:.0f} in on roads near you", NEARBY))
    ww = h.waterway or "the nearest creek"
    if h.in_warning and h.gauge_rising:
        out.append((Level.DANGER, f"{ww} is rising fast inside the warning", NEARBY))
    if rain_heavy and h.gauge_rising:
        out.append((Level.WARNING, f"Heavy rain and {ww} rising", NEARBY))
    if h.closure_nearby:
        out.append((Level.WARNING, f"Flooded road reported near you: {h.closure_nearby}", NEARBY))
    if CATEGORY_RANK.get(h.gauge_category, -1) >= CATEGORY_RANK["minor"]:
        out.append((Level.WARNING, f"{ww} is in {h.gauge_category} flood", NEARBY))
    if CATEGORY_RANK.get(h.forecast_category, -1) >= CATEGORY_RANK["minor"]:
        out.append((Level.WATCH, f"{ww} forecast to reach {h.forecast_category} flood", NEARBY))
    if rain_heavy:
        out.append((Level.WATCH, f"Heavy rain ({h.rain_in_hr:.1f} in/hr)", NEARBY))
    for a in h.ahead:
        wet = a.point_status in WET_STATUSES or (a.depth_in or 0.0) >= danger
        out.append((Level.DANGER if wet else Level.WARNING, f"Water ahead on {a.road_name} in {a.distance_m:.0f} m", AHEAD))
    for r in h.route:
        out.append((Level.WARNING, f"Your planned route crosses water on {r.road_name}", AHEAD))
    return out


def classify_hazard(h: LocationHazard, stall_depth_in: float, driving: bool = False,
                    cfg: Mapping[str, Any] | None = None) -> tuple[Level, tuple[str, ...]]:
    """Evidence only (vulnerability is applied later). Returns the level and the reasons that set it, worst first."""
    c: Mapping[str, Any] = cfg if cfg is not None else safety_settings()
    found = _findings(h, stall_depth_in, c)
    hag = h.height_above_water_m
    if h.coverage != "region":
        # Alerts alone can't place water at you: cap at WARNING (an Emergency keeps DANGER).
        found = [(lv if kind != ALERT or h.emergency_polygon else min(lv, Level.WARNING), why, kind)
                 for lv, why, kind in found]
    elif not driving and (h.far_from_water or (hag is not None and hag >= float(c["high_ground_m"]))):
        # At rest on high ground: area-wide alerts are a WATCH, water nearby is at most a WARNING (your exits).
        soft = {ALERT: Level.WATCH, NEARBY: Level.WARNING}
        found = [(min(lv, soft[kind]) if kind in soft else lv, why, kind) for lv, why, kind in found]
    if not found:
        return Level.NONE, ()
    level = max(lv for lv, _, _ in found)
    reasons = [why for lv, why, _ in sorted(found, key=lambda x: -x[0])]
    return level, tuple(dict.fromkeys(reasons))
