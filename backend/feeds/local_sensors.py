"""Public regional sensors and source context. Parsing here is a temporary map projection."""

import asyncio
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from feeds.base import fetch_live_page
from feeds.intake import FeedRequest, RawEnvelope, split_response

LCRA = FeedRequest("lcra_hydromet", "lcra_sites", "https://hydromet.lcra.org/api/GetDataForAllSites",
                   {}, {"state": "TX", "basin": "Lower Colorado"}, "array", 12)
HARRIS = FeedRequest("hcfcd_water_levels", "hcfcd_sites", "https://www.harriscountyfws.org/Home/GetSiteRecentData",
                     {"regionId": 1, "timeSpan": 2}, {"state": "TX", "county": "Harris"}, "features", 12)
CAMERAS = FeedRequest("txdot_cameras", "txdot_camera_catalog", "https://its.txdot.gov/its/Map/GetIconModelsOfType",
                      {"type": "camera"}, {"state": "TX"}, "array", 12)
INUNDATION = "https://inundation.hcfcd.org/api/Layer/Exists/"
CENTRAL = ZoneInfo("America/Chicago")


def local_time(value: object) -> str | None:
    """Interpret source wall times with DST, rejecting ambiguous/nonexistent instants."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo:
            return stamp.astimezone(UTC).isoformat()
        first = stamp.replace(tzinfo=CENTRAL, fold=0)
        second = stamp.replace(tzinfo=CENTRAL, fold=1)
        if first.utcoffset() != second.utcoffset():
            return None
        if first.astimezone(UTC).astimezone(CENTRAL).replace(tzinfo=None) != stamp:
            return None
        return first.astimezone(UTC).isoformat()
    except ValueError:
        return None


async def _collect(request: FeedRequest, id_field: str) -> list[RawEnvelope]:
    response = await fetch_live_page(request.product, request.url, request.params, request.timeout_s)
    rows = split_response(request, response)
    result = []
    for row in rows:
        body = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        properties = body.get("properties", body)
        identifier = properties.get(id_field) if isinstance(properties, dict) else None
        metadata = row.provider_metadata
        if request.source_id == "txdot_cameras":
            identifier = None
            # Per-row hint: copy, because split_response shares one metadata dict across a response's rows.
            metadata = {**metadata, "logical_key_hint": [body.get("name"), body.get("lon"), body.get("lat")]}
        result.append(replace(row, source_record_id=str(identifier) if identifier is not None else None,
                              provider_metadata=metadata))
    return result


async def collect_inundation() -> list[RawEnvelope]:
    now = datetime.now(CENTRAL)
    latest = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
    for interval in range(3):
        stamp = latest - timedelta(minutes=interval * 30)
        layer = stamp.strftime("%Y%m%d%H%M")
        request = FeedRequest("hcfcd_inundation", "hcfcd_layer", INUNDATION + layer,
                              {}, {"state": "TX", "county": "Harris"}, "array", 8)
        response = await fetch_live_page(request.product, request.url, {}, request.timeout_s)
        if response["source"] != "live":
            return split_response(request, response)
        if response["data"] is True or response["data"] == "true":
            response["data"] = [{"id": layer, "layer": layer, "layer_time_local": stamp.replace(tzinfo=None).isoformat(),
                                 "exists": True, "tile_template": f"https://inundation.hcfcd.org/api/Tiles/{layer}/{{quadkey}}"}]
            return split_response(request, response)
    response["data"] = []
    return split_response(request, response)


async def collect_local_sensors() -> list[RawEnvelope]:
    batches = await asyncio.gather(_collect(LCRA, "siteNumber"), _collect(HARRIS, "SiteId"),
                                   _collect(CAMERAS, "owner"), collect_inundation())
    return [row for batch in batches for row in batch]


def _point(lon: object, lat: object) -> dict | None:
    try:
        x, y = float(lon), float(lat)
        if math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90:
            return {"type": "Point", "coordinates": [x, y]}
    except (ValueError, TypeError):
        pass
    return None


def _value(value: object) -> str:
    try:
        number = float(value)
        return str(value) if math.isfinite(number) and number not in (-9999, -1) else "unknown"
    except (ValueError, TypeError):
        return "unknown"


def preview_local(raw: RawEnvelope) -> dict | None:
    if raw.retrieval_status != "success" or not isinstance(raw.raw_payload, dict):
        return None
    body = raw.raw_payload
    if raw.source_id == LCRA.source_id:
        return {"title": str(body.get("siteName") or body.get("siteNumber")),
                "detail": f"1-hour rainfall {_value(body.get('rainfall1Hour'))} in · stage {_value(body.get('stage'))} ft (datum unverified) · provisional",
                "time": body.get("dateTime"), "geometry": _point(body.get("longitude"), body.get("latitude")),
                "evidence_type": "measurement", "timestamp_role": "observation", "link": "https://hydromet.lcra.org/"}
    if raw.source_id == HARRIS.source_id:
        props = body.get("properties") if isinstance(body.get("properties"), dict) else {}
        streams = props.get("StreamData")
        readings = [r for r in streams if isinstance(r, dict)] if isinstance(streams, list) else []
        reading = max(readings, key=lambda r: local_time(r.get("CurrentReadingDate")) or "", default={})
        geo = body.get("geometry") if isinstance(body.get("geometry"), dict) else {}
        xy = geo.get("coordinates") or []
        return {"title": str(geo.get("Text") or props.get("SiteId")),
                "detail": f"Water level {_value(reading.get('CurrentLevel'))} ft · vertical reference requires site metadata · {len(streams) if isinstance(streams, list) else 0} sensors",
                "time": local_time(reading.get("CurrentReadingDate")),
                "geometry": _point(*xy[:2]) if len(xy) >= 2 else None,
                "evidence_type": "measurement", "timestamp_role": "observation",
                "link": "https://www.harriscountyfws.org/"}
    if raw.source_id == CAMERAS.source_id:
        return {"title": str(body.get("name") or body.get("owner")), "detail": f"Camera catalog · provider active flag {body.get('isActive')} · capture time unavailable",
                "time": None, "geometry": _point(body.get("lon"), body.get("lat")), "evidence_type": "context",
                "timestamp_role": "unknown", "link": "https://its.txdot.gov/its/map"}
    if raw.source_id == "hcfcd_inundation":
        return {"title": "Harris County inundation layer", "detail": f"Model layer {body.get('layer')} exists · open county map for depth bands · raster not decoded",
                "time": local_time(body.get("layer_time_local")), "geometry": None, "evidence_type": "model",
                "timestamp_role": "model_run", "link": "https://www.harriscountyfws.org/"}
    return None
