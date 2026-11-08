"""Live (real DJI Tello) drone routes. Contract: docs/api-contract.md, "Live drone".

The backend never talks to the drone directly. It forwards to the Tello bridge
(backend/scripts/tello_dashboard.py, its own venv), which owns the drone's UDP ports and
safety logic. An offline bridge is a normal state: status reports it and the UI shows
cached footage, so the offline demo never depends on a drone.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.security import require_trusted_origin

router = APIRouter(prefix="/api/live-drone", tags=["live-drone"])

FALLBACK_IMAGE_URL = "/static/drone/flood_03.jpg"
STATUS_TIMEOUT = httpx.Timeout(1.5)
COMMAND_TIMEOUT = httpx.Timeout(3.0)
GAUGE_COMMAND_TIMEOUT = httpx.Timeout(8.0)  # a press can overlap the bridge loading the gauge model
VIDEO_TIMEOUT = httpx.Timeout(5.0, read=None)  # MJPEG never "finishes"
RC_LIMIT = 100
STATUS_FIELDS = (
    "connected", "flying", "busy", "battery", "temp", "height", "tof", "flight_time",
    "speed", "attitude", "state_age", "video_age", "log",
)
MJPEG_TYPE = "multipart/x-mixed-replace; boundary=frame"

_transport: httpx.AsyncBaseTransport | None = None  # tests swap in a MockTransport


def bridge_url() -> str:
    return os.environ.get("TELLO_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")


def _client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=bridge_url(), timeout=timeout, transport=_transport)


class RcIn(BaseModel):
    lr: int = Field(0, ge=-RC_LIMIT, le=RC_LIMIT)
    fb: int = Field(0, ge=-RC_LIMIT, le=RC_LIMIT)
    ud: int = Field(0, ge=-RC_LIMIT, le=RC_LIMIT)
    yaw: int = Field(0, ge=-RC_LIMIT, le=RC_LIMIT)


@router.get("/status")
async def status() -> dict[str, Any]:
    base = {"fallback_image_url": FALLBACK_IMAGE_URL, "controls_url": bridge_url()}
    try:
        async with _client(STATUS_TIMEOUT) as client:
            response = await client.get("/status")
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return {**base, "bridge": "offline"}
    if not isinstance(data, dict) or "connected" not in data:
        return {**base, "bridge": "outdated"}  # an old bridge build: restart tello_dashboard.py
    return {**{k: data[k] for k in STATUS_FIELDS if k in data}, **base, "bridge": "online"}


async def _forward(path: str, payload: dict[str, Any], timeout: httpx.Timeout = COMMAND_TIMEOUT) -> dict[str, Any]:
    try:
        async with _client(timeout) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:  # the bridge is up but slow: not the same as offline
        raise HTTPException(status_code=504, detail="Tello bridge did not answer in time, try again") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Tello bridge is offline") from exc


@router.post("/action/{action}", dependencies=[Depends(require_trusted_origin)])
async def action(action: Literal["takeoff", "land", "emergency"]) -> dict[str, Any]:
    return await _forward(f"/action/{action}", {})


@router.post("/rc", dependencies=[Depends(require_trusted_origin)])
async def rc(body: RcIn) -> dict[str, Any]:
    return await _forward("/rc", body.model_dump())


@router.get("/video")
async def video() -> StreamingResponse:
    client = _client(VIDEO_TIMEOUT)
    try:
        upstream = await client.send(client.build_request("GET", "/video"), stream=True)
        upstream.raise_for_status()
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=503, detail="Tello bridge is offline") from exc

    async def relay():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    media_type = upstream.headers.get("content-type", MJPEG_TYPE)
    return StreamingResponse(relay(), media_type=media_type, headers={"Cache-Control": "no-store"})


# ---------- gauge tray water level (contract: "Gauge tray water level") ----------

JPEG_TYPE = "image/jpeg"
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/gauge")
async def gauge_status() -> dict[str, Any]:
    try:
        async with _client(STATUS_TIMEOUT) as client:
            response = await client.get("/gauge/status")
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return {"gauge": "offline"}
    if not isinstance(data, dict) or "gauge" not in data:
        return {"gauge": "offline"}  # a bridge build without the gauge routes
    return data


class CornersIn(BaseModel):
    """Four clicked tray corners in frame pixels (tag-free pose), or clear=true to forget them."""
    points: list[tuple[float, float]] | None = Field(None, min_length=4, max_length=4)
    clear: bool = False


# Declared before /gauge/{command}: FastAPI doesn't fall through to the next route on a 422.
@router.post("/gauge/corners", dependencies=[Depends(require_trusted_origin)])
async def gauge_corners(body: CornersIn) -> dict[str, Any]:
    if not body.clear and body.points is None:
        raise HTTPException(status_code=422, detail="send 4 points or clear=true")
    payload = {"clear": True} if body.clear else {"points": [list(p) for p in body.points or []]}
    return await _forward("/gauge/corners", payload, GAUGE_COMMAND_TIMEOUT)


@router.post("/gauge/{command}", dependencies=[Depends(require_trusted_origin)])
async def gauge_command(command: Literal["baseline", "start", "stop"]) -> dict[str, Any]:
    return await _forward(f"/gauge/{command}", {}, GAUGE_COMMAND_TIMEOUT)


@router.get("/gauge/overlay.jpg")
async def gauge_overlay() -> Response:
    try:
        async with _client(COMMAND_TIMEOUT) as client:
            response = await client.get("/gauge/overlay.jpg")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Tello bridge is offline") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="No gauge reading yet")
    if response.is_error or not response.headers.get("content-type", "").startswith(JPEG_TYPE):
        raise HTTPException(status_code=503, detail="Tello bridge has no gauge overlay")
    return Response(content=response.content, media_type=JPEG_TYPE, headers=NO_STORE)
