"""Replay gauges for the ops map: July 4, 2025 USGS stage series plus NWS flood categories (NWPS).

    cd backend && uv run python -m scripts.build_wx_gauges
Writes data/wx/gauges.json. Gauges NWS doesn't categorize get categories=null (shown gray in the UI).
Also carries the replay's NWS warning timeline (config/regions/hill_country.yaml) for the top bar.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

import yaml

from app.config import DATA_DIR, REPO_DIR

HYDRO = DATA_DIR / "region" / "hill_country" / "hydrographs_2025-07-04.json"
OUT = DATA_DIR / "wx" / "gauges.json"
REGION_CONFIG = REPO_DIR / "backend" / "config" / "regions" / "hill_country.yaml"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges/{site}"
USER_AGENT = "HiTide-HackUTD/1.0 (offline demo cache)"
WINDOW_UTC = ("2025-07-04T04:00:00+00:00", "2025-07-04T14:00:00+00:00")  # replay 06-12:30Z, with margin
CATEGORIES = ("action", "minor", "moderate", "major")
NWPS_MISSING = -9999


def nws_gauge(site: str) -> dict:
    req = urllib.request.Request(NWPS.format(site=site), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https host
            d = json.load(r)
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"  {site}: NWPS lookup failed ({e}); no categories", file=sys.stderr)
        return {"lid": None, "categories": None}
    cats = (d.get("flood") or {}).get("categories") or {}
    stages = {k: (cats.get(k) or {}).get("stage") for k in CATEGORIES}
    usable = all(isinstance(v, (int, float)) and v != NWPS_MISSING for v in stages.values())
    return {"lid": d.get("lid"), "categories": stages if usable else None}


def main() -> int:
    hydro = json.loads(HYDRO.read_text())
    lo, hi = WINDOW_UTC
    gauges = []
    for site, rec in hydro["gauges"].items():
        series = [[t, v] for t, v in rec["series"] if lo <= t <= hi]
        nws = nws_gauge(site)
        gauges.append({"site": site, "name": rec["name"], "lon": rec["lon"], "lat": rec["lat"],
                       "nws_lid": nws["lid"], "categories_ft": nws["categories"], "series": series})
        print(f"  {site} {nws['lid']}: {len(series)} readings, categories {nws['categories']}")
    warnings = yaml.safe_load(REGION_CONFIG.read_text())["replay"]["warnings"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": hydro["source"] + "; flood categories from NWS NWPS",
                               "gauges": gauges, "warnings": warnings}, separators=(",", ":"), default=str))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
