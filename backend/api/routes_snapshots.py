"""POST /api/snapshots: drone vision snapshots in (overview 15), `snapshot.created` out over /ws."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import DATA_DIR
from app.security import require_trusted_origin
from vision.bridge import apply_to_loop
from vision.snapshot import VisionSnapshot

log = logging.getLogger(__name__)
SNAPSHOT_DIR = (DATA_DIR / "drone_samples" / "snapshots").resolve()
router = APIRouter(prefix="/api/snapshots", tags=["Drone vision"], dependencies=[Depends(require_trusted_origin)])


def _image_exists(url: str) -> bool:
    # url already matched ^/static/drone/snapshots/<safe name>.jpg$; still resolve and confine the path
    path = (SNAPSHOT_DIR / url.rsplit("/", 1)[-1]).resolve()
    return path.is_relative_to(SNAPSHOT_DIR) and path.is_file()


def _server_alerts(snap: VisionSnapshot) -> VisionSnapshot:
    """Alerts are derived on the server from the snapshot's vehicles/people (a client can't inject or drop them)."""
    from vision.alerts import rules
    from vision.config import vision_config

    alerts = rules([v.model_dump() for v in snap.vehicles], [p.model_dump() for p in snap.people],
                   snap.est_depth_in, vision_config()["alerts"])
    return VisionSnapshot.model_validate({**snap.model_dump(), "alerts": [a.__dict__ for a in alerts]})


class SnapshotAck(BaseModel):
    accepted: bool
    fused: bool
    not_fused_reason: str | None
    alerts: int


@router.post("", status_code=202, response_model=SnapshotAck,
             responses={403: {"description": "untrusted origin"}, 422: {"description": "invalid snapshot"},
                        503: {"description": "Hill Country scenario failed to load"}})
async def post_snapshot(snap: VisionSnapshot, request: Request) -> SnapshotAck:
    token = os.environ.get("VISION_INGEST_TOKEN")
    if token and not hmac.compare_digest(request.headers.get("x-vision-token", ""), token):
        raise HTTPException(status_code=403, detail="missing or wrong X-Vision-Token")
    snap = _server_alerts(snap)
    if snap.image_url is not None and not await asyncio.to_thread(_image_exists, snap.image_url):
        raise HTTPException(status_code=422, detail="image_url does not exist on the server")
    return await ingest(request.app, snap)


async def ingest(app: Any, snap: VisionSnapshot) -> SnapshotAck:
    """Shared by POST /api/snapshots and the live Tello flight: fuse into the loop, then broadcast."""
    fused, why = False, "not a critical point"
    if snap.point_id.startswith("cp-"):
        from app.hill_runtime import get_hill

        hill = await get_hill(app)
        fused, why = await asyncio.to_thread(apply_to_loop, hill.loop, snap)
    payload = snap.model_dump(mode="json")
    try:  # state is already updated; a broadcast problem must not turn into a 500 that clients retry
        await app.state.runtime.hub.emit("snapshot.created", payload)
    except Exception:
        log.exception("snapshot.created broadcast failed for %s", snap.point_id)
    log.info("snapshot %s wet=%s depth=%s conf=%s fused=%s", snap.point_id, snap.water_on_road,
             snap.est_depth_in, snap.confidence, fused)
    return SnapshotAck(accepted=True, fused=fused, not_fused_reason=why or None, alerts=len(snap.alerts))
