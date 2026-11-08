"""NOAA raw intake and temporary display projections, without raster interpretation."""

import asyncio
import gzip
import json
import math
import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import numpy as np
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds
from shapely.geometry import Point, Polygon

from app.config import REPO_DIR
from feeds.base import USER_AGENT, fetch_live_page
from feeds.intake import RawEnvelope

NWPS_URL = "https://api.water.noaa.gov/nwps/v1/gauges"
TEXAS_BBOX = {"bbox.xmin": -106.7, "bbox.ymin": 25.8, "bbox.xmax": -93.5,
              "bbox.ymax": 36.6, "srid": "EPSG_4326"}
GRID_PRODUCTS = (
    ("noaa_mrms", "PrecipRate", "https://mrms.ncep.noaa.gov/2D/PrecipRate/",
     "MRMS_PrecipRate", "Rainfall rate", "mm/hour", "measurement"),
    ("noaa_flash", "CREST_MAXUNITSTREAMFLOW",
     "https://mrms.ncep.noaa.gov/2D/FLASH/CREST_MAXUNITSTREAMFLOW/",
     "MRMS_FLASH_CREST_MAXUNITSTREAMFLOW", "Modeled maximum unit streamflow",
     "m3/s/km2", "model"),
)


def envelope(source_id: str, url: str, payload, *, record_id=None, status="success",
             errors=(), metadata=None, params=None) -> RawEnvelope:
    now = datetime.now(UTC).isoformat()
    return RawEnvelope(
        source_id=source_id, source_record_id=record_id, attempt_id=str(uuid4()),
        retrieved_at=now, payload_retrieved_at=now if status != "failed" else None,
        request_params=params or {}, geographic_scope={"state": "TX"},
        provider_metadata={"endpoint": url, **(metadata or {})}, raw_payload=payload,
        provenance="unavailable" if status == "failed" else "live",
        retrieval_status=status, errors=tuple(errors),
    )


def newest_grib_reference(html: str, prefix: str) -> tuple[str, str] | None:
    """Use immutable product time, not the mutable latest alias or HTTP Date."""
    pattern = rf'href="({re.escape(prefix)}_[0-9.]+_(\d{{8}}-\d{{6}})\.grib2\.gz)"'
    candidates = re.findall(pattern, html)
    if not candidates:
        return None
    name, stamp = max(candidates, key=lambda item: item[1])
    return name, datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC).isoformat()


async def collect_grid(product: tuple) -> list[RawEnvelope]:
    source, code, url, prefix, meaning, _unit, evidence_type = product
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url)
            response.raise_for_status()
        newest = newest_grib_reference(response.text, prefix)
    except (httpx.HTTPError, ValueError):
        return [envelope(source, url, None, status="failed", errors=("catalog_unavailable",))]
    if newest is None:
        return [envelope(source, url, {"catalog": response.text[:2000]}, status="malformed",
                         errors=("missing_timestamped_grib",))]
    name, _timestamp = newest
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            binary = await client.get(url + name)
            binary.raise_for_status()
        samples = await asyncio.to_thread(decode_texas_grid, binary.content)
    except (httpx.HTTPError, OSError, ValueError, EOFError, KeyError):
        return [envelope(source, url, None, status="failed", errors=("grid_decode_failed",))]
    if not samples:
        return [envelope(source, url, None, status="malformed", errors=("no_texas_grid_values",))]
    attempt = str(uuid4())
    return [replace(envelope(source, url, {
        "product": code, "storage_reference": url + name, "format": "GRIB2+gzip",
        "product_time": sample["time"], "meaning": meaning, "unit": sample["unit"],
        "grib_time_metadata": sample["time_metadata"],
        "value": sample["value"], "geometry": sample["geometry"],
        "grid_cell_degrees": 0.5, "aggregation": "maximum_of_nonnegative_pixels",
        "temporal_meaning": "maximum forecast guidance" if source == "noaa_flash" else "instantaneous radar estimate",
        "temporal_horizon": "version-dependent; verify before decision use" if source == "noaa_flash" else None,
        "original_crs": sample["crs"], "raster_decoded": True,
    }, record_id=f'{name}:{index}', metadata={"evidence_type": evidence_type,
        "timestamp_role": "product_time", "http_status": response.status_code}),
        attempt_id=attempt, record_index=index) for index, sample in enumerate(samples)]


def decode_texas_grid(compressed: bytes) -> list[dict]:
    """Coarse-cell previews with explicit aggregation, never road depth."""
    rings = json.loads((REPO_DIR / "frontend/src/evidence/texasBoundary.json").read_text())["rings"]
    polygons = [Polygon(ring) for ring in rings]
    result = []
    with MemoryFile(gzip.decompress(compressed)) as memory, memory.open() as dataset:
        tags = dataset.tags(1)
        stamp = datetime.fromtimestamp(int(tags["GRIB_VALID_TIME"]), UTC).isoformat()
        for lat in np.arange(26.0, 36.5, 0.5):
            for lon in np.arange(-106.5, -93.5, 0.5):
                if not any(p.covers(Point(lon, lat)) for p in polygons):
                    continue
                window = from_bounds(lon - .25, lat - .25, lon + .25, lat + .25,
                                     dataset.transform).round_offsets().round_lengths()
                pixels = dataset.read(1, window=window)
                good = pixels[np.isfinite(pixels) & (pixels >= 0)]
                if good.size:
                    result.append({"value": float(good.max()), "time": stamp,
                        "unit": tags.get("GRIB_UNIT", ""), "crs": str(dataset.crs),
                            "time_metadata": {key: tags.get(key) for key in (
                                "GRIB_REF_TIME", "GRIB_VALID_TIME", "GRIB_FORECAST_SECONDS")},
                        "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}})
    return result


async def collect_nwps() -> list[RawEnvelope]:
    response = await fetch_live_page("noaa_nwps", NWPS_URL, TEXAS_BBOX, 25)
    if response["source"] != "live":
        return [envelope("noaa_nwps", NWPS_URL, None, status="failed",
                         errors=response.get("errors", ()), params=TEXAS_BBOX)]
    data = response.get("data")
    gauges = data.get("gauges") if isinstance(data, dict) else None
    if not isinstance(gauges, list):
        return [envelope("noaa_nwps", NWPS_URL, data, status="malformed",
                         errors=("unexpected_gauge_collection",), params=TEXAS_BBOX)]
    results = []
    for gauge in gauges:
        if not isinstance(gauge, dict):
            results.append(envelope("noaa_nwps", NWPS_URL, gauge, status="malformed",
                                    errors=("unexpected_gauge_record",), params=TEXAS_BBOX))
            continue
        state = gauge.get("state")
        if not isinstance(state, dict) or state.get("abbreviation") != "TX":
            continue
        results.append(envelope("noaa_nwps", NWPS_URL, gauge, record_id=gauge.get("lid"),
                                metadata=response.get("provider_metadata"), params=TEXAS_BBOX))
    if results:
        attempt = results[0].attempt_id
        return [replace(row, attempt_id=attempt, record_index=i) for i, row in enumerate(results)]
    return [envelope("noaa_nwps", NWPS_URL, data, status="empty", params=TEXAS_BBOX)]


async def collect_noaa_products() -> list[RawEnvelope]:
    batches = await asyncio.gather(collect_nwps(), *(collect_grid(p) for p in GRID_PRODUCTS))
    return [row for batch in batches for row in batch]


def preview_noaa(raw: RawEnvelope) -> dict | None:
    """Minimal display projection. Future normalization must preserve all original fields."""
    if raw.retrieval_status != "success" or not isinstance(raw.raw_payload, dict):
        return None
    payload = raw.raw_payload
    if raw.source_id in ("noaa_mrms", "noaa_flash"):
        link = payload.get("storage_reference")
        if not isinstance(link, str) or not link.startswith("https://mrms.ncep.noaa.gov/2D/"):
            return None
        return {"title": payload.get("meaning", "NOAA grid"),
                "detail": f'{payload.get("value"):.3g} {payload.get("unit")} - spatial maximum in 0.5 degree cell; {payload.get("temporal_meaning", "area context")}',
                "time": payload.get("product_time"), "geometry": payload.get("geometry"),
                "value": payload.get("value"), "unit": payload.get("unit"),
                "evidence_type": "model" if raw.source_id == "noaa_flash" else "measurement",
                "timestamp_role": "product_valid_time" if raw.source_id == "noaa_flash" else "observation",
                "link": link}
    if raw.source_id != "noaa_nwps":
        return None
    status = payload.get("status")
    observed = status.get("observed") if isinstance(status, dict) else None
    if not isinstance(observed, dict):
        return None
    value, unit = observed.get("primary"), observed.get("primaryUnit")
    if (not isinstance(value, (float, int)) or isinstance(value, bool)
            or not math.isfinite(value) or value in (-999, -9999) or not unit):
        return None
    lon, lat = payload.get("longitude"), payload.get("latitude")
    if not all(type(n) in (float, int) and math.isfinite(n) for n in (lon, lat)):
        return None
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        return None
    return {"title": payload.get("name") or payload.get("lid") or "NWPS station",
            "detail": f"Observed level {value} {unit} · {observed.get('floodCategory', 'unknown category')}",
            "time": observed.get("validTime"),
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "evidence_type": "measurement", "timestamp_role": "observation",
            "link": "https://water.noaa.gov/gauges/" + str(payload.get("lid", "")).lower()}
