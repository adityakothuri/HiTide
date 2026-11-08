"""REST + WebSocket routes. Contract: docs/api-contract.md."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from api.schemas import DroneCommandIn, ReplyIn
from outreach.inbound import handle_inbound

from app.hill_runtime import get_hill, set_mode, start_replay
from app.data_mode import current_modes
from app.runtime import Runtime
from app.security import origin_ok, require_trusted_origin
from feeds import Scope, all_feeds
from feeds.recent import RecentSnapshot, map_response, recent_feeds

log = logging.getLogger(__name__)
router = APIRouter()

def rt(request: Request) -> Runtime:
    return request.app.state.runtime


@router.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    r = rt(request)
    return {"ok": True, "segments": len(r.town.edge_ids), "drivers": len(r.drivers), "ws_clients": r.hub.client_count,
            "modes": current_modes(_region_mode_now(request), _db_now(request)),
            "database": db.public() if (db := getattr(request.app.state, "db", None)) is not None else None}


def _db_now(request: Request) -> str | None:
    """The database actually in use, e.g. "spacetime" or "sqlite (fallback: SpacetimeDB unreachable ...)"."""
    db = getattr(request.app.state, "db", None)
    return db.describe() if db is not None else None


def _region_mode_now(request: Request) -> str | None:
    """Region mode without waiting for the Hill Country build (health must stay instant)."""
    task = getattr(request.app.state, "hill_task", None)
    if task is None or not task.done() or task.cancelled() or task.exception() is not None:
        return None
    return task.result().mode


@router.get("/api/town")
async def town(request: Request) -> dict[str, Any]:
    t = rt(request).town
    w, s, e, n = t.bounds
    return {"segments": t.segments_fc, "river": t.river_feature, "bounds": [w, s, e, n],
            "center": [(s + n) / 2, (w + e) / 2]}


@router.get("/api/state")
async def state(request: Request) -> dict[str, Any]:
    return rt(request).snapshot()


@router.get("/api/feeds")
async def feeds() -> dict[str, Any]:
    return await all_feeds()


Scenario = Literal["kerrville", "hill_country"]


async def _stop_hill(request: Request) -> None:
    if getattr(request.app.state, "hill_task", None) is not None and request.app.state.hill_task.done():
        hill = await get_hill(request.app)
        await set_mode(hill, "replay")  # stops the replay or live monitoring, clears, emits region.reset


@router.get("/api/feeds/recent")
async def recent(request: Request, max_age_minutes: int = Query(30, ge=15, le=30),
                 scope: Scope = "texas", map_view: bool = False) -> dict[str, Any]:
    if not hasattr(request.app.state, "recent_snapshots"):
        request.app.state.recent_snapshots = {}
    snapshots = request.app.state.recent_snapshots
    if scope not in snapshots:
        snapshots[scope] = RecentSnapshot()
    result = await recent_feeds(max_age_minutes, scope, snapshots[scope])
    return map_response(result) if map_view else result


@router.post("/api/demo/start", dependencies=[Depends(require_trusted_origin)])
async def demo_start(request: Request, scenario: Scenario = "kerrville",
                     speed: float = Query(150.0, ge=10.0, le=1000.0)) -> dict[str, Any]:
    """One scenario at a time: starting either stops the other. `speed` applies to hill_country."""
    if scenario == "hill_country":
        hill = await get_hill(request.app)
        await rt(request).reset()
        await start_replay(hill, speed)
        return {"ok": True, "scenario": scenario, "speed": speed}
    await _stop_hill(request)
    r = rt(request)
    await r.reset()
    r.demo.start()
    return {"ok": True, "scenario": scenario}


@router.post("/api/demo/reset", dependencies=[Depends(require_trusted_origin)])
async def demo_reset(request: Request, scenario: Scenario = "kerrville") -> dict[str, Any]:
    if scenario == "hill_country":
        hill = await get_hill(request.app)
        await set_mode(hill, hill.mode)  # clean state; live restarts monitoring, replay waits for start
        return {"ok": True, "scenario": scenario, "mode": hill.mode}
    await rt(request).reset()
    return {"ok": True, "scenario": scenario}


@router.get("/api/cases")
async def cases(request: Request) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in rt(request).sorted_cases()]


@router.post("/api/drones/{drone_id}/command", dependencies=[Depends(require_trusted_origin)])
async def drone_command(drone_id: str, body: DroneCommandIn, request: Request) -> dict[str, Any]:
    case = await rt(request).runner.drone_command(drone_id, body.command)
    if case is None:
        raise HTTPException(status_code=404, detail="drone not found")
    return case.model_dump(mode="json")


@router.post("/api/cases/{case_id}/reply", dependencies=[Depends(require_trusted_origin)])
async def case_reply(case_id: str, body: ReplyIn, request: Request) -> dict[str, Any]:
    case = await rt(request).runner.reply(case_id, body.reply, "driver")
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case.model_dump(mode="json")


class InboundIn(BaseModel):
    sender: str = Field(alias="from", max_length=40)
    text: str = Field(max_length=500)


@router.post("/api/photon/inbound")
async def photon_inbound(body: InboundIn, request: Request) -> dict[str, Any]:
    """Replies from the Photon sidecar. Only allowlisted demo numbers can affect a case."""
    expected = os.environ.get("SIDECAR_KEY", "")
    given = request.headers.get("x-sidecar-key", "").encode()
    if not expected or not hmac.compare_digest(given, expected.encode()):
        raise HTTPException(status_code=401, detail="bad sidecar key")
    return await handle_inbound(rt(request), body.sender, body.text)


@router.get("/api/drivers/{driver_id}")
async def driver_view(driver_id: str, request: Request) -> dict[str, Any]:
    r = rt(request)
    d = next((x for x in r.drivers if x.id == driver_id), None)
    if d is None:
        raise HTTPException(status_code=404, detail="driver not found")
    w = r.runner.world
    cid = w.case_by_driver.get(driver_id)
    return {
        "driver": {**r.runner.driver_public(d), "vehicle": f"{d.vehicle.make} {d.vehicle.model}"},
        "alert": r.engine.alert,
        "pretrip_warning": w.pretrip_cards.get(driver_id),
        "active_turn_around": w.turn_arounds.get(driver_id),
        "case": w.cases[cid].model_dump(mode="json") if cid else None,
    }


@router.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    r: Runtime = websocket.app.state.runtime
    if not origin_ok(websocket.headers.get("origin")):
        await websocket.close(code=1008)  # policy violation: untrusted page
        return
    await r.hub.connect(websocket, r.snapshot)
    try:
        while True:  # clients don't send; just keep the socket open until it closes
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await r.hub.disconnect(websocket)
