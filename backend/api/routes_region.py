"""Hill Country replay API (docs/api-contract.md "Hill Country scenario"). Bodies are pre-encoded JSON:
the static map is encoded once, state is an immutable snapshot built under the loop lock after each step."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.hill_runtime import RegionMode, get_hill, set_mode, state_json
from app.security import require_trusted_origin
from critical.flood_layer import build_flood_layer, geometry_index, parse_bbox
from critical.route_options import edge_statuses, nearest_node, route_options
from drone.dispatch import distance_m

log = logging.getLogger(__name__)
router = APIRouter()
_tello_lock = asyncio.Lock()  # one real flight at a time (two clients would fight over the UDP port)
JSON = "application/json"


@router.get("/api/region")
async def region(request: Request) -> Response:
    return Response((await get_hill(request.app)).static_json, media_type=JSON)


@router.get("/api/region/state")
async def region_state(request: Request) -> Response:
    return Response(state_json(await get_hill(request.app)), media_type=JSON)


def _part(key: str):
    async def handler(request: Request) -> Response:
        return Response(json.dumps((await get_hill(request.app)).loop.snapshot.get(key, [])).encode(), media_type=JSON)
    return handler


@router.get("/api/region/sources")
async def region_sources(request: Request) -> dict:
    """Which evidence sources drive detection right now, their provenance and the age of their newest data."""
    hill = await get_hill(request.app)
    if hill.mode == "live" and hill.live is not None:  # current even between loop steps
        return {"mode": "live", "sources": {k: v.public() for k, v in hill.live.sources().items()}}
    return {"mode": hill.mode, "sources": {k: v.public() for k, v in hill.replay_obs.sources.items()}}


@router.post("/api/region/mode", dependencies=[Depends(require_trusted_origin)])
async def region_mode(request: Request, mode: RegionMode) -> dict:
    """replay: July 4, 2025 (start with /api/demo/start?scenario=hill_country). live: real-time Texas feeds now."""
    hill = await get_hill(request.app)
    await set_mode(hill, mode)
    return {"ok": True, "mode": hill.mode}


router.add_api_route("/api/region/critical-points", _part("critical_points"), methods=["GET"])
router.add_api_route("/api/region/nodes", _part("nodes"), methods=["GET"])
router.add_api_route("/api/region/gauges", _part("gauges"), methods=["GET"])  # small: the phone app polls this


_FLOOD_CACHE: dict[tuple, dict] = {}
_FLOOD_CACHE_MAX = 8  # a few map windows x the current step; older entries fall out first


@router.get("/api/region/flood-layer")
async def flood_layer(request: Request, bbox: str) -> dict:
    """Flooded / likely / unknown roads with geometry, crossings, gauges and alerts inside one map window."""
    try:
        box = parse_bbox(bbox)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"bbox: {exc}") from exc
    hill = await get_hill(request.app)
    loop = hill.loop
    index = await asyncio.to_thread(geometry_index, loop.region)

    def build() -> dict:
        with loop.lock:  # the replay steps in a worker thread
            snapshot, status = loop.snapshot, dict(loop.status)
        # The snapshot is replaced (never mutated) each step; sim_time guards against a recycled id().
        key = (box, id(snapshot), snapshot.get("sim_time"))
        cached = _FLOOD_CACHE.get(key)
        if cached is None:
            cached = build_flood_layer(snapshot, loop.points, status, index, box)
            if len(_FLOOD_CACHE) >= _FLOOD_CACHE_MAX:
                _FLOOD_CACHE.pop(next(iter(_FLOOD_CACHE)))
            _FLOOD_CACHE[key] = cached
        return cached

    return await asyncio.to_thread(build)
router.add_api_route("/api/region/drones/plan", _part("drones"), methods=["GET"])


@router.post("/api/region/drones/tello", dependencies=[Depends(require_trusted_origin)])
async def fly_tello(request: Request) -> dict:
    """DRONE_MODE=tello: fly the real Tello on drone 1's current first leg (scaled indoors), post its snapshot."""
    if os.environ.get("DRONE_MODE", "sim") != "tello":
        raise HTTPException(status_code=409, detail="DRONE_MODE is not 'tello'")
    from drone.tello import fly_first_leg

    hill = await get_hill(request.app)
    loop = hill.loop
    with loop.lock:  # the replay steps drones in a worker thread
        drone = next((d for d in loop.drones.values() if d.target), None)
        if drone is None:
            raise HTTPException(status_code=409, detail="no drone has a target yet; start the replay first")
        drone_id, target, leg_from = drone.id, dict(loop.points[drone.target]), tuple(drone.leg_from)
    bearing = math.degrees(math.atan2((target["lon"] - leg_from[0]) * math.cos(math.radians(target["lat"])),
                                      target["lat"] - leg_from[1])) % 360
    dist = distance_m(leg_from[1], leg_from[0], target["lat"], target["lon"])
    if _tello_lock.locked():
        raise HTTPException(status_code=409, detail="the Tello is already flying")
    async with _tello_lock:
        res = await asyncio.to_thread(fly_first_leg, bearing, dist)
    if not res.ok:  # failure drill: the task fails, the previous status stands
        return {"ok": False, "error": res.error, "point_id": target["id"]}
    vision = await _vision_snapshot(res, target["id"], drone_id)
    if vision is not None:  # the drone's frames went through the vision model
        from api.routes_snapshots import ingest

        try:
            ack = await ingest(request.app, vision)
            return {"ok": True, "vision": True, "fused": ack.fused, "not_fused_reason": ack.not_fused_reason,
                    "snapshot": vision.model_dump(mode="json")}
        except Exception:  # never lose a good flight: fall back to the HSV result below
            log.exception("vision snapshot ingest failed for %s; using the HSV cover result", target["id"])
    snap = loop.external_snapshot(target["id"], drone_id, res.water_on_road, res.road_covered_pct)
    await request.app.state.runtime.hub.emit("snapshot.created", {"scenario": "hill_country", **snap})
    return {"ok": True, "vision": False, "snapshot": snap}


async def _vision_snapshot(res, point_id: str, drone_id: str):
    """Tello hover frames -> vision model. None (HSV fallback) if the vision extra/models aren't installed."""
    if not res.keyframes or os.environ.get("TELLO_VISION", "1") == "0":
        return None
    try:
        from vision.live import run_hover

        return await asyncio.to_thread(run_hover, res.keyframes, point_id, drone_id, time.time())
    except Exception:  # any model failure (cv2.error, torch, missing weights) -> HSV fallback, flight kept
        log.exception("vision model unavailable for the Tello hover; using the HSV cover fallback")
        return None


def _lon_lat(raw: str, name: str, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    try:
        lon, lat = (float(v) for v in raw.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{name} must be 'lon,lat'") from exc
    if not (math.isfinite(lon) and math.isfinite(lat)) or not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        raise HTTPException(status_code=422, detail=f"{name} is outside the region")
    return lon, lat


@router.get("/api/routes/options")
async def routes_options(request: Request, start: str, end: str) -> dict:
    """Up to 3 different ways from start to end ('lon,lat'), each with the flooding reported on it.
    The first is the plain fastest way (it may cross water); the others avoid known flooding. Never called safe."""
    hill = await get_hill(request.app)
    loop = hill.loop
    rb = loop.region.cfg["bbox"]  # {west, south, east, north}
    bbox = (float(rb["west"]), float(rb["south"]), float(rb["east"]), float(rb["north"]))
    a = _lon_lat(start, "start", bbox)
    b = _lon_lat(end, "end", bbox)
    index = await asyncio.to_thread(geometry_index, loop.region)

    def build() -> list[dict]:
        with loop.lock:
            snapshot, status = loop.snapshot, dict(loop.status)
        u, v = nearest_node(index, *a), nearest_node(index, *b)
        if not u or not v or u == v:
            return []
        edges = edge_statuses(snapshot.get("segments", []), loop.point_of, status)
        return [o.public() for o in route_options(loop.graph, index, edges, u, v)]

    return {"at": loop.snapshot.get("sim_time"), "options": await asyncio.to_thread(build)}
