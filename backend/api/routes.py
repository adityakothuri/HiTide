"""REST + WebSocket routes. Contract: docs/api-contract.md."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.runtime import Runtime
from feeds import all_feeds

log = logging.getLogger(__name__)
router = APIRouter()

SIM_ALERT = {
    "id": "sim-ffw-kerrville",
    "event": "Flash Flood Warning",
    "headline": "SIMULATED: Flash Flood Warning for Kerr County. Guadalupe River rising rapidly. Turn around, don't drown.",
    "active": True,
    "simulated": True,
    "polygon": None,
}


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
    r.engine.reset()
    await r.engine.begin_flood(SIM_ALERT)
    return {"ok": True}


@router.post("/api/demo/reset")
async def demo_reset(request: Request) -> dict[str, Any]:
    r = rt(request)
    r.engine.reset()
    await r.hub.emit("snapshot", r.snapshot())
    return {"ok": True}


@router.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    r: Runtime = websocket.app.state.runtime
    await r.hub.connect(websocket, r.snapshot())
    try:
        while True:
            await websocket.receive_text()  # clients don't send; keep the socket open
    except WebSocketDisconnect:
        pass
    finally:
        await r.hub.disconnect(websocket)
