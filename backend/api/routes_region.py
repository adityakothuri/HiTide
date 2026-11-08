"""Hill Country replay API (docs/api-contract.md "Hill Country scenario")."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.hill_runtime import get_hill, state

router = APIRouter()


@router.get("/api/region")
async def region(request: Request) -> dict[str, Any]:
    return (await get_hill(request.app)).static


@router.get("/api/region/state")
async def region_state(request: Request) -> dict[str, Any]:
    return state(await get_hill(request.app))


@router.get("/api/region/critical-points")
async def critical_points(request: Request) -> list[dict[str, Any]]:
    return (await get_hill(request.app)).loop.ranked_public()


@router.get("/api/region/nodes")
async def nodes(request: Request) -> list[dict[str, Any]]:
    loop = (await get_hill(request.app)).loop
    return [loop.node_public(n) for n in loop.nodes]


@router.get("/api/region/drones/plan")
async def drones_plan(request: Request) -> list[dict[str, Any]]:
    loop = (await get_hill(request.app)).loop
    return [d.public(loop.t or 0.0) for d in loop.drones.values()]
