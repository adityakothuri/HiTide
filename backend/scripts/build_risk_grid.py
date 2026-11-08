"""Flood Risk Index frames for the July 4, 2025 replay: Float32 grids (0..100) over the Hunt -> Kerrville DEM.

Terrain (height above nearest waterway, distance to it) from data/region/hill_country/{dem30.npz,
waterways.geojson}; rain from the cached recolored MRMS tiles in data/wx/mrms (bins inverted back to inches).
Model and weights: config/risk_grid.yaml and scoring/risk_grid.py. Runs offline.

    cd backend && uv run python -m scripts.build_risk_grid
Writes frontend/public/grids/{index.json, study_area.geojson, <id>.bin, <id>.factors.bin}.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from shapely.geometry import MultiPoint, mapping, shape

from app.config import BACKEND_DIR, DATA_DIR, REPO_DIR
from scoring.risk_grid import (
    aggregate_cells, cell_bounds, combine, decode_ramp, dist_risk, encode_factors, encode_frame,
    forecast_rain, hand_risk, rain_risk, top_two,
)
from scripts.fetch_mrms_tiles import RAMP
from sim.depth_grid import river_reference

REGION = DATA_DIR / "region" / "hill_country"
MRMS = DATA_DIR / "wx" / "mrms"
OUT = REPO_DIR / "frontend" / "public" / "grids"
CONFIG = BACKEND_DIR / "config" / "risk_grid.yaml"
M_PER_DEG_LAT = 111_320.0
CDT = timedelta(hours=-5)
TILE_PX = 256
FACTOR_LABELS = ["Low height above stream", "Near a waterway", "Rain, past hour", "Rain, past 24 h"]


def _block_min(z: np.ndarray, block: int) -> np.ndarray:
    h, w = (z.shape[0] // block) * block, (z.shape[1] // block) * block
    b = np.where(np.isnan(z[:h, :w]), np.inf, z[:h, :w]).reshape(h // block, block, w // block, block)
    m = b.min(axis=(1, 3))
    return np.where(np.isinf(m), np.nan, m)


def load_grid(block: int) -> dict:
    d = np.load(REGION / "dem30.npz")
    raw = d["z"].astype(float)
    z = aggregate_cells(raw, block)
    z_min = _block_min(raw, block)
    dx, dy = float(d["dx"]) * block, float(d["dy"]) * block
    x0, y0 = float(d["x0"]), float(d["y0"])
    lat_mid = y0 + z.shape[0] * dy / 2
    cell_m = math.sqrt(abs(dx) * M_PER_DEG_LAT * math.cos(math.radians(lat_mid)) * abs(dy) * M_PER_DEG_LAT)
    lon = x0 + (np.arange(z.shape[1]) + 0.5) * dx
    lat = y0 + (np.arange(z.shape[0]) + 0.5) * dy
    return {"z": z, "z_min": z_min, "x0": x0, "y0": y0, "dx": dx, "dy": dy, "cell_m": cell_m, "lon": lon, "lat": lat}


def rasterize_waterways(g: dict, sample_m: float) -> tuple[np.ndarray, np.ndarray]:
    """(river mask, bed elevation m per river cell, NaN elsewhere). Profiled waterways carry a bed profile
    from the 10 m DEM (non-increasing downstream); other streams fall back to the lowest 30 m DEM cell."""
    h, w = g["z"].shape
    mask = np.zeros((h, w), dtype=bool)
    bed = np.full((h, w), np.inf)
    step = sample_m / M_PER_DEG_LAT

    def cells(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        col = np.floor((lon - g["x0"]) / g["dx"]).astype(int)
        row = np.floor((lat - g["y0"]) / g["dy"]).astype(int)
        return row, col, (row >= 0) & (row < h) & (col >= 0) & (col < w)  # no clamping onto the edge

    for f in json.loads((REGION / "waterways.geojson").read_text())["features"]:
        line = shape(f["geometry"])
        pts = np.array([line.interpolate(d).coords[0] for d in np.arange(0.0, line.length + step, step)])
        row, col, keep = cells(pts[:, 0], pts[:, 1])
        mask[row[keep], col[keep]] = True
        prof = np.array(f["properties"].get("bed") or [], dtype=float).reshape(-1, 4)
        if prof.size:
            row, col, keep = cells(prof[:, 1], prof[:, 2])
            np.minimum.at(bed, (row[keep], col[keep]), prof[keep, 3])
    bed = np.where(np.isinf(bed), g["z_min"], bed)
    return mask, np.where(mask, bed, np.nan)


def mercator_px(lon: np.ndarray, lat: np.ndarray, z: int) -> tuple[np.ndarray, np.ndarray]:
    n = TILE_PX * 2 ** z
    r = np.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - np.arcsinh(np.tan(r)) / np.pi) / 2.0 * n


def sample_rain(product: str, stamp: str, g: dict, zoom: int, top_in: float) -> np.ndarray:
    """Inches at every cell centre from the recolored tiles; missing tiles read as no data (NaN)."""
    lon, lat = np.meshgrid(g["lon"], g["lat"])
    px, py = mercator_px(lon, lat, zoom)
    px, py = px.astype(int), py.astype(int)
    tx, ty = px // TILE_PX, py // TILE_PX
    out = np.full(lon.shape, np.nan)
    for x in np.unique(tx):
        for y in np.unique(ty[tx == x]):
            path = MRMS / product / stamp / str(zoom) / str(x) / f"{y}.png"
            if not path.exists():
                # A silent gap would show as NaN holes inside the study area; fail so the cache gets fixed.
                raise FileNotFoundError(f"MRMS tile missing: {path}")
            inches = decode_ramp(np.asarray(Image.open(path).convert("RGBA")), RAMP, top_in)
            sel = (tx == x) & (ty == y)
            out[sel] = inches[py[sel] % TILE_PX, px[sel] % TILE_PX]
    return out


def frame_times(cfg: dict) -> list[datetime]:
    t0 = datetime.fromisoformat(cfg["start_utc"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(cfg["end_utc"].replace("Z", "+00:00"))
    step = timedelta(minutes=cfg["step_min"])
    n = int((t1 - t0) / step)
    return [t0 + k * step for k in range(n + 1)]


def stamp_at(t: datetime, stamps: list[str]) -> str:
    """Newest completed MRMS hour at or before t (accumulations are stamped at their end)."""
    ok = [s for s in stamps if datetime.strptime(s, "%Y%m%d%H").replace(tzinfo=UTC) <= t]
    return ok[-1] if ok else stamps[0]


def study_area(valid: np.ndarray, g: dict) -> dict:
    rows, cols = np.nonzero(valid)
    pts = MultiPoint(list(zip(g["lon"][cols].round(5), g["lat"][rows].round(5))))
    hull = pts.convex_hull.buffer(abs(g["dx"]) / 2, join_style=2).simplify(abs(g["dx"]) / 2)
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": "Hunt to Kerrville"}, "geometry": mapping(hull)}]}


def write_frame(fid: str, t: datetime, kind: str, comps: dict, cfg: dict, valid: np.ndarray, rain1h_in: np.ndarray) -> dict:
    index, contrib = combine(comps, cfg["weights"], cfg["rain"]["floor"])
    index = np.where(valid, index, np.nan)
    ok = ~np.isnan(index)
    top, second = top_two(contrib)
    (OUT / f"{fid}.bin").write_bytes(encode_frame(index))
    (OUT / f"{fid}.factors.bin").write_bytes(encode_factors(top, second, ok))
    lo, hi, mean = float(np.nanmin(index)), float(np.nanmax(index)), float(np.nanmean(index))
    print(f"  {fid} {kind:8s} min {lo:5.1f} max {hi:5.1f} mean {mean:5.2f}  >=50: {int((index >= 50).sum())}")
    return {"id": fid, "time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "kind": kind,
            "url": f"grids/{fid}.bin", "factors_url": f"grids/{fid}.factors.bin",
            "min": round(lo, 2), "max": round(hi, 2),
            # Study-area past-hour rain (inches) for the time bar's rain histogram.
            "rain1h_max": round(float(np.nanmax(np.where(valid, rain1h_in, np.nan))), 2),
            "rain1h_mean": round(float(np.nanmean(np.where(valid, rain1h_in, np.nan))), 3)}


def frame_id(t: datetime) -> str:
    return (t + CDT).strftime("%Y-%m-%dT%H%M")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    g = load_grid(cfg["grid"]["block"])
    h, w = g["z"].shape
    print(f"Grid {w}x{h}, cell ~{g['cell_m']:.0f} m")
    river, bed = rasterize_waterways(g, cfg["grid"]["river_sample_m"])
    z_ref, dist = river_reference(bed, river, g["cell_m"])  # nearest waterway's bed and distance to it
    terrain = {"hand": hand_risk(g["z_min"] - z_ref, cfg["terrain"]["hand_max_m"]),
               "dist": dist_risk(dist, cfg["terrain"]["dist_scale_m"])}
    valid = ~np.isnan(g["z"]) & np.isfinite(z_ref)
    rc, fc = cfg["rain"], cfg["frames"]
    stamps = json.loads((MRMS / "manifest.json").read_text())["stamps_utc"]

    def rain(stamp: str) -> tuple[np.ndarray, np.ndarray]:
        r1 = sample_rain("p1h", stamp, g, rc["tile_zoom"], rc["top_bin_in"])
        r24 = sample_rain("p24h", stamp, g, rc["tile_zoom"], rc["top_bin_in"])
        return r1, r24

    def comps(r1: np.ndarray, r24: np.ndarray) -> dict:
        return {**terrain, "rain1h": rain_risk(r1, rc["rain1h_norm_in"]),
                "rain24h": rain_risk(r24, rc["rain24h_norm_in"])}

    frames, cache = [], {}
    for t in frame_times(fc):
        stamp = stamp_at(t, stamps)
        cache.setdefault(stamp, rain(stamp))
        frames.append(write_frame(frame_id(t), t, "observed", comps(*cache[stamp]), cfg, valid, cache[stamp][0]))
    last_t, (r1, r24) = t, cache[stamp]
    for k in range(1, fc["forecast_steps"] + 1):
        ft = last_t + timedelta(minutes=fc["step_min"] * k)
        r1k = forecast_rain(r1, k, fc["forecast_decay_1h"])
        frames.append(write_frame(frame_id(ft), ft, "forecast", comps(r1k, r24), cfg, valid, r1k))

    west, south, east, north = cell_bounds(g["x0"], g["y0"], g["dx"], g["dy"], w, h)
    index = {"version": 1, "name": "Flood risk index", "study_area": "Hunt to Kerrville",
             "bounds": [round(v, 6) for v in (west, south, east, north)], "width": w, "height": h,
             "cell_m": cfg["grid"]["cell_m"], "factors": FACTOR_LABELS, "frames": frames}
    (OUT / "index.json").write_text(json.dumps(index, indent=1, allow_nan=False))
    (OUT / "study_area.geojson").write_text(json.dumps(study_area(valid, g)))
    size = sum(p.stat().st_size for p in OUT.iterdir()) / 1e6
    print(f"Wrote {len(frames)} frames to {OUT} ({size:.1f} MB)")
    for f in (frames[0], max(frames, key=lambda f: f["max"]), frames[-fc["forecast_steps"] - 1]):
        probe(g, f["id"], w)
    return 0


def probe(g: dict, fid: str, w: int) -> None:
    """Sanity print: river corridor near Kerrville vs the highest-ground cell, on the last observed frame."""
    a = np.frombuffer((OUT / f"{fid}.bin").read_bytes(), dtype="<f4").reshape(-1, w)
    for name, lon, lat in (("Guadalupe @ Kerrville", -99.1431, 30.0464), ("Guadalupe @ Hunt", -99.335, 30.0705)):
        r, c = int((lat - g["y0"]) / g["dy"]), int((lon - g["x0"]) / g["dx"])
        win = a[max(r - 3, 0):r + 4, max(c - 3, 0):c + 4]
        print(f"  {fid} {name}: max nearby {np.nanmax(win):.1f}")
    rr, cc = np.unravel_index(np.nanargmax(g["z"]), g["z"].shape)
    print(f"  {fid} ridge top ({g['lon'][cc]:.4f}, {g['lat'][rr]:.4f}, {g['z'][rr, cc]:.0f} m): {a[rr, cc]:.1f}")


if __name__ == "__main__":
    raise SystemExit(main())
