"""Cache the real July 3-5, 2025 USGS gage-height series for the region's gauges. Needs network once.

    uv run python -m scripts.fetch_july2025

Writes data/region/<id>/hydrographs_2025-07-04.json:
  {"site": {"name", "waterway", "lon", "lat", "datum_ft", "series": [[iso_utc, stage_ft], ...]}}
Gaps stay gaps: the Hunt gauge (08165500) stopped reporting after 37.52 ft at 10:10Z (05:10 CDT).
"""

from __future__ import annotations

import json
import sys
import time

import httpx

from scripts.build_region_cache import BACKEND, load_region

OGC = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"
WINDOW = "2025-07-03T00:00:00Z/2025-07-06T00:00:00Z"
HEADERS = {"User-Agent": "FloodWatch-HackUTD/0.1 (demo cache build)"}


def _get(client: httpx.Client, url: str, params: dict, attempts: int = 3) -> dict:
    resp = client.get(url, params=params)
    for attempt in range(1, attempts):
        if resp.status_code == 200:
            break
        print(f"  HTTP {resp.status_code} (attempt {attempt})")
        time.sleep(2 * attempt)
        resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def fetch_site(client: httpx.Client, site: str) -> dict:
    loc = _get(client, f"{OGC}/monitoring-locations/items/USGS-{site}", {"f": "json"})
    lon, lat = loc["geometry"]["coordinates"][:2]
    datum = loc["properties"].get("altitude")
    data = _get(client, f"{OGC}/continuous/items", {
        "monitoring_location_id": f"USGS-{site}", "parameter_code": "00065",
        "datetime": WINDOW, "limit": 10000, "f": "json"})
    series = sorted((f["properties"]["time"], float(f["properties"]["value"]))
                    for f in data.get("features", []) if f["properties"].get("value") not in (None, ""))
    return {"lon": lon, "lat": lat, "datum_ft": datum, "series": [[t, v] for t, v in series]}


def main(region_id: str = "hill_country") -> int:
    region = load_region(region_id)
    out = BACKEND.parent / "data" / "region" / region_id / "hydrographs_2025-07-04.json"
    result = {}
    with httpx.Client(timeout=30, headers=HEADERS, follow_redirects=False) as client:
        for g in region["gauges"]:
            rec = fetch_site(client, g["site"])
            rec.update(name=g["name"], waterway=g["waterway"])
            result[g["site"]] = rec
            peak = max(rec["series"], key=lambda p: p[1]) if rec["series"] else None
            print(f"  {g['site']} {g['name']}: {len(rec['series'])} pts, peak {peak}")
    out.write_text(json.dumps({"source": "USGS Water Data OGC API, parameter 00065 (gage height, ft), approved",
                               "window": WINDOW, "gauges": result}, indent=1))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
