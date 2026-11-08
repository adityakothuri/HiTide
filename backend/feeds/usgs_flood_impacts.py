"""USGS Real-Time Flood Impacts (RTFI) reference points for the Kerrville gage.

Docs: https://api.waterdata.usgs.gov/rtfi-api/docs
Each reference point is a surveyed feature (bank, road, building, ...) with the gage
height (rp_elevation, ft) at which it floods.
"""

from __future__ import annotations

from typing import Any

from feeds.base import fetch_with_fallback

RTFI_BASE = "https://api.waterdata.usgs.gov/rtfi-api"
NWIS_SITE = "08166200"


def _simplify_point(rp: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rp.get("id"),
        "name": rp.get("rp_name"),
        "description": rp.get("description"),
        "lat": rp.get("latitude"),
        "lon": rp.get("longitude"),
        "flood_stage_ft": rp.get("rp_elevation"),
        "current_gage_ft": rp.get("gage_height"),
        "is_flooding": bool(rp.get("is_flooding")),
        "nws_id": rp.get("nws_id"),
    }


def simplify_impacts(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    points = [_simplify_point(rp) for rp in data if isinstance(rp, dict)]
    return sorted(points, key=lambda p: p["flood_stage_ft"] if p["flood_stage_ft"] is not None else float("inf"))


async def flood_impacts() -> dict[str, Any]:
    """Envelope plus `impacts`: reference points sorted by flood stage (lowest first)."""
    envelope = await fetch_with_fallback("usgs_flood_impacts", f"{RTFI_BASE}/referencepoints/nwis/{NWIS_SITE}")
    return {**envelope, "simulated": False, "impacts": simplify_impacts(envelope["data"])}
