"""Cache archived MRMS rainfall tiles (Iowa Environmental Mesonet) for the July 4, 2025 replay.

IEM's tiles use a ramp that starts in saturated blue, which drowns the blue flood-depth layer. Each pixel is
decoded back to inches (IEM legend strip + its tick marks) and redrawn with an NWS-style precipitation
ramp (greens, yellow, red, magenta), transparent under 0.01 in.

Raw tiles: data/wx_cache/mrms_raw/ (not shipped). Recolored: data/wx/mrms/{p1h,p24h}/{YYYYMMDDHH}/{z}/{x}/{y}.png
plus manifest.json with the stamps and the legend for the ramp actually drawn.

    cd backend && uv run python -m scripts.fetch_mrms_tiles
"""

from __future__ import annotations

import io
import json
import math
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import DATA_DIR

OUT = DATA_DIR / "wx" / "mrms"
RAW = DATA_DIR / "wx_cache" / "mrms_raw"
IEM = "https://mesonet.agron.iastate.edu"
TILE_URL = IEM + "/cache/tile.py/1.0.0/mrms::{product}-{stamp}00/{z}/{x}/{y}.png"
LEGEND_URL = IEM + "/images/mrms_q3_{product}.png"
USER_AGENT = "FloodWatch-HackUTD/1.0 (offline demo cache)"

KERR_COUNTY = (-99.76, 29.78, -98.92, 30.29)  # west, south, east, north
ZOOMS = range(8, 12)  # MRMS is ~1 km; z11 is ~76 m per pixel, the map overzooms past it
FIRST_HOUR_UTC = datetime(2025, 7, 4, 6, tzinfo=UTC)  # 01:00 CDT
LAST_HOUR_UTC = datetime(2025, 7, 4, 13, tzinfo=UTC)  # 08:00 CDT, covers the 07:30 end
PRODUCTS = ("p1h", "p24h")
WORKERS = 4

# Tick positions measured on IEM's 256 px p24h legend strip (x pixel -> inches); nonlinear above 1 in.
# The archived mrms::p1h tiles use this same scale, not the linear 1-9 in p1h legend image: decoded with the
# p1h image, Hunt's hourly totals 01-07 CDT summed to 19.6 in against a 7.9 in 24 h total; with this scale
# they sum to ~8 in, matching (checked 2026-11-07 at Hunt and Kerrville).
TICKS = [(25, "0.25"), (50, "0.5"), (75, "0.75"), (100, "1"), (119, "2"), (139, "3"), (160, "4"),
         (179, "5"), (189, "7"), (205, "10"), (230, "15")]
SCALE_LEGEND = "p24h"
STRIP_ROW = 5
# NWS-style precipitation ramp: (lower bound in inches, color). Under the first bound is transparent.
# The two lightest bins carry alpha (8-digit hex) so widespread drizzle doesn't blanket the basemap.
RAMP = [(0.01, "#a8e6a140"), (0.1, "#6cc46a99"), (0.25, "#2f9a3f"), (0.5, "#f4e04d"), (0.75, "#f0b43c"),
        (1.0, "#ec8a2f"), (1.5, "#e0522b"), (2.0, "#c02427"), (3.0, "#d63fa0"), (4.0, "#9a4fcf"),
        (6.0, "#e6d6f2")]
LABELLED = {0.1, 0.5, 1.0, 2.0, 3.0, 6.0}  # every bin labelled would crowd a 250 px colorbar


def tile_range(z: int) -> tuple[range, range]:
    west, south, east, north = KERR_COUNTY
    n = 2 ** z

    def xy(lon: float, lat: float) -> tuple[int, int]:
        r = math.radians(lat)
        return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * n)

    x0, y0 = xy(west, north)
    x1, y1 = xy(east, south)
    return range(x0, x1 + 1), range(y0, y1 + 1)


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def stamps() -> list[str]:
    hours = int((LAST_HOUR_UTC - FIRST_HOUR_UTC).total_seconds() // 3600)
    return [(FIRST_HOUR_UTC + timedelta(hours=h)).strftime("%Y%m%d%H") for h in range(hours + 1)]


def fetch_tile(job: tuple[str, str, int, int, int]) -> str | None:
    product, stamp, z, x, y = job
    path = RAW / product / stamp / str(z) / str(x) / f"{y}.png"
    if path.exists():
        return None
    try:
        data = get(TILE_URL.format(product=product, stamp=stamp, z=z, x=x, y=y))
    except urllib.error.URLError as e:
        return f"{product} {stamp} {z}/{x}/{y}: {e}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return None


def strip_values() -> dict[tuple[int, int, int], float]:
    """IEM legend strip color -> inches, interpolating between the measured tick marks (x=0 is 0 in)."""
    im = Image.open(io.BytesIO(get(LEGEND_URL.format(product=SCALE_LEGEND)))).convert("RGB")
    xs = [0] + [x for x, _ in TICKS]
    vals = [0.0] + [float(label) for _, label in TICKS]
    runs: dict[tuple[int, int, int], list[int]] = {}
    for x in range(1, im.width - 1):
        rgb = im.getpixel((x, STRIP_ROW))
        if rgb != (0, 0, 0):  # the strip's border pixel
            runs.setdefault(rgb, []).append(x)
    # A color spanning several pixels (saturated red) takes the middle of its run.
    return {rgb: float(np.interp(sum(r) / len(r), xs, vals)) for rgb, r in runs.items()}


def recolor(src: Path, dst: Path, lookup: dict[tuple[int, int, int], float],
            keys: np.ndarray, key_vals: np.ndarray) -> None:
    rgba = np.asarray(Image.open(src).convert("RGBA"))
    flat = rgba.reshape(-1, 4)
    opaque = flat[:, 3] > 0
    colors, inverse = np.unique(flat[:, :3], axis=0, return_inverse=True)
    vals = np.array([lookup.get(tuple(int(v) for v in c)) if tuple(int(v) for v in c) in lookup
                     else float(key_vals[np.argmin(((keys - c.astype(int)) ** 2).sum(1))]) for c in colors])
    inches = np.where(opaque, vals[inverse.ravel()], 0.0)
    bounds = np.array([b for b, _ in RAMP])
    palette = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] + [int(h[7:9] or "ff", 16)] for _, h in RAMP],
                       dtype=np.uint8)
    idx = np.searchsorted(bounds, inches, side="right") - 1
    out = np.where((idx >= 0)[:, None], palette[np.clip(idx, 0, None)], 0).astype(np.uint8)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.reshape(rgba.shape), "RGBA").save(dst, optimize=True)


def ramp_legend() -> dict:
    n = len(RAMP)
    stops = [{"pos": round(p, 4), "color": c} for i, (_, c) in enumerate(RAMP) for p in (i / n, (i + 1) / n)]
    ticks = [{"pos": round(i / n, 4), "label": f"{b:g}"} for i, (b, _) in enumerate(RAMP) if b in LABELLED]
    return {"stops": stops, "ticks": ticks, "units": "in"}


def main() -> int:
    jobs = [(p, s, z, x, y) for p in PRODUCTS for s in stamps() for z in ZOOMS
            for x in tile_range(z)[0] for y in tile_range(z)[1]]
    print(f"Fetching {len(jobs)} MRMS tiles ({len(stamps())} hours x {len(PRODUCTS)} products)...")
    with ThreadPoolExecutor(WORKERS) as pool:
        errors = [e for e in pool.map(fetch_tile, jobs) if e]
    for e in errors:
        print("  failed:", e, file=sys.stderr)
    lookup = strip_values()
    for p in PRODUCTS:
        keys = np.array(list(lookup), dtype=int)
        key_vals = np.array(list(lookup.values()))
        for src in sorted((RAW / p).rglob("*.png")):
            recolor(src, OUT / src.relative_to(RAW), lookup, keys, key_vals)
        print(f"  recolored {p}")
    manifest = {
        "source": "MRMS QPE via Iowa Environmental Mesonet tile cache (archived)",
        "bbox": KERR_COUNTY,
        "minzoom": min(ZOOMS),
        "maxzoom": max(ZOOMS),
        "stamps_utc": stamps(),
        "ramp": "NWS-style precipitation ramp, recolored from IEM tiles; transparent under 0.01 in",
        "products": {p: {"label": "1 hour" if p == "p1h" else "24 hours", "legend": ramp_legend()} for p in PRODUCTS},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"Wrote {OUT / 'manifest.json'} ({len(errors)} failures)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
