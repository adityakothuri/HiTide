"""REST + WebSocket routes. Contract: docs/api-contract.md."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from api.schemas import ReplyIn

from app.runtime import Runtime
from feeds import all_feeds

log = logging.getLogger(__name__)
router = APIRouter()

def rt(request: Request) -> Runtime:
    return request.app.state.runtime


@router.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    r = rt(request)
    return {"ok": True, "segments": len(r.town.edge_ids), "drivers": len(r.drivers), "ws_clients": r.hub.client_count}


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


@router.post("/api/demo/start")
async def demo_start(request: Request) -> dict[str, Any]:
    r = rt(request)
    await r.reset()
    r.demo.start()
    return {"ok": True}


@router.post("/api/demo/reset")
async def demo_reset(request: Request) -> dict[str, Any]:
    await rt(request).reset()
    return {"ok": True}


@router.get("/api/cases")
async def cases(request: Request) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in rt(request).sorted_cases()]


@router.post("/api/cases/{case_id}/reply")
async def case_reply(case_id: str, body: ReplyIn, request: Request) -> dict[str, Any]:
    case = await rt(request).runner.reply(case_id, body.reply, "driver")
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case.model_dump(mode="json")


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
