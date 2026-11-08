"""REST + WebSocket routes. Contract: docs/api-contract.md."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from api.schemas import ReplyIn
from outreach.inbound import handle_inbound

from app.runtime import Runtime
from app.security import origin_ok, require_trusted_origin
from feeds import Scope, all_feeds
from feeds.recent import RecentSnapshot, recent_feeds

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


@router.get("/api/feeds/recent")
async def recent(request: Request, max_age_minutes: int = Query(30, ge=15, le=30),
                 scope: Scope = "texas") -> dict[str, Any]:
    if not hasattr(request.app.state, "recent_snapshots"):
        request.app.state.recent_snapshots = {}
    snapshots = request.app.state.recent_snapshots
    if scope not in snapshots:
        snapshots[scope] = RecentSnapshot()
    return await recent_feeds(max_age_minutes, scope, snapshots[scope])


@router.post("/api/demo/start", dependencies=[Depends(require_trusted_origin)])
async def demo_start(request: Request) -> dict[str, Any]:
    r = rt(request)
    await r.reset()
    r.demo.start()
    return {"ok": True}


@router.post("/api/demo/reset", dependencies=[Depends(require_trusted_origin)])
async def demo_reset(request: Request) -> dict[str, Any]:
    await rt(request).reset()
    return {"ok": True}


@router.get("/api/cases")
async def cases(request: Request) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in rt(request).sorted_cases()]


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
