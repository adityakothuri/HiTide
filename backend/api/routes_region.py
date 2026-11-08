"""Hill Country replay API (docs/api-contract.md "Hill Country scenario"). Bodies are pre-encoded JSON:
the static map is encoded once, state is an immutable snapshot built under the loop lock after each step."""

from __future__ import annotations

import asyncio
import json
import math
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.hill_runtime import get_hill, state_json
from app.security import require_trusted_origin
from drone.dispatch import distance_m

router = APIRouter()
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


router.add_api_route("/api/region/critical-points", _part("critical_points"), methods=["GET"])
router.add_api_route("/api/region/nodes", _part("nodes"), methods=["GET"])
router.add_api_route("/api/region/drones/plan", _part("drones"), methods=["GET"])


@router.post("/api/region/drones/tello", dependencies=[Depends(require_trusted_origin)])
async def fly_tello(request: Request) -> dict:
    """DRONE_MODE=tello: fly the real Tello on drone 1's current first leg (scaled indoors), post its snapshot."""
    if os.environ.get("DRONE_MODE", "sim") != "tello":
        raise HTTPException(status_code=409, detail="DRONE_MODE is not 'tello'")
    from drone.tello import fly_first_leg

    hill = await get_hill(request.app)
    loop = hill.loop
    drone = next((d for d in loop.drones.values() if d.target), None)
    if drone is None:
        raise HTTPException(status_code=409, detail="no drone has a target yet; start the replay first")
    target = loop.points[drone.target]
    bearing = math.degrees(math.atan2((target["lon"] - drone.leg_from[0]) * math.cos(math.radians(target["lat"])),
                                      target["lat"] - drone.leg_from[1])) % 360
    dist = distance_m(drone.leg_from[1], drone.leg_from[0], target["lat"], target["lon"])
    res = await asyncio.to_thread(fly_first_leg, bearing, dist)
    if not res.ok:  # failure drill: the task fails, the previous status stands
        return {"ok": False, "error": res.error, "point_id": target["id"]}
    snap = loop.external_snapshot(target["id"], drone.id, res.water_on_road, res.road_covered_pct)
    await request.app.state.runtime.hub.emit("snapshot.created", {"scenario": "hill_country", **snap})
    return {"ok": True, "snapshot": snap}
