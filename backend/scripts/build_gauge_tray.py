"""Build the one-piece "gauge tray": a printable flood diorama the drone camera reads water depth from.

    cd backend && uv run --with pillow python -m scripts.build_gauge_tray

Idea: every surface the camera sees sits at a KNOWN printed height. The valley is stepped in exact
terraces (STEP_MM each = 1 ft of flood rise); a low-water crossing with a stranded car and
houses at several elevations give familiar reference heights. Pour dyed water in; the camera
finds where the waterline sits on those known heights and reads the depth off the truth heightmap.

One watertight body (a closed heightfield), sized for a Bambu P1P (256 mm bed). Writes data/gauge_tray/:
  gauge_tray.stl   the print
  truth.npz        heightmap (mm) the camera sees + fiducial corners (vision ground truth)
  manifest.json    size, levels (mm <-> ft), pour table (mL per level), feature positions, tags
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[2] / "data" / "gauge_tray"
STL_HEADER = b"FloodWatch gauge tray (model mm)".ljust(80, b" ")

SIZE_MM = 200.0              # square footprint (P1P bed is 256)
RES_MM = 0.4                 # heightfield grid = one nozzle width
RIM_MM = 10.0
RIM_TOP_MM = 22.0
FLOOR_MM = 1.6               # river channel floor (base thickness under the deepest point)
POOL_MM = 4.0                # normal river surface = gauge zero
STEP_MM = 2.0                # one terrace = one gauge step = "1 ft" of rise (multiple of 0.2 mm layers)
TOP_STEP = 7                 # highest terrace is POOL + 7 steps (18 mm); keeps the print low
CHANNEL_HALF_MM = 9.0
PAD_MM = 26.0                # corner pads for the ArUco tags, flush with the rim
TAG_MM = 20.0
TAG_RECESS_MM = 0.4          # pocket that locates the paper tag exactly
TAG_IDS = (0, 1, 2, 3)       # SW, SE, NE, NW (same as the old tabletop tray)
EMBOSS_MM = 0.6              # raised lettering / numbers

ROAD_Y_MM = 122.0
ROAD_HALF_MM = 4.6
ROAD_LIFT_MM = 0.4
DECK_MM = POOL_MM + 0.6      # low-water crossing deck: just above normal flow
ROAD_RAMP = 0.16             # mm rise per mm away from the river on the approach
DASH_MM, GAP_MM, DASH_HALF_MM, DASH_DEPTH_MM = 4.0, 3.0, 0.45, 0.4

POUR_LEVELS = 7              # pour table: normal pool up to this many steps

FONT_CANDIDATES = ("C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


# ---------------------------------------------------------------- geometry helpers
def river_centre(y: np.ndarray) -> np.ndarray:
    """x of the river centreline (mm) for a given y: one gentle meander north to south."""
    t = (y - RIM_MM) / (SIZE_MM - 2 * RIM_MM)
    return SIZE_MM / 2 + 26.0 * np.sin(2 * np.pi * 0.85 * t + 0.5)


def creek_line() -> np.ndarray:
    """Quinlan Creek: enters from the east rim and joins the river south of the road."""
    t = np.linspace(0, 1, 300)
    x = SIZE_MM + 15 - t * (SIZE_MM + 15 - float(river_centre(np.array(62.0))))
    y = 38 + 24 * t + 7 * np.sin(np.pi * 2.2 * t)
    return np.column_stack([x, y])


def polyline_distance(gx: np.ndarray, gy: np.ndarray, line: np.ndarray) -> np.ndarray:
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    best = np.full(len(pts), np.inf)
    for k in range(0, len(line), 40):
        seg = line[k:k + 40]
        best = np.minimum(best, np.sqrt(((pts[:, None, :] - seg[None, :, :]) ** 2).sum(-1)).min(1))
    return best.reshape(gx.shape)


def river_distance(gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """True distance (mm) from every grid point to the river centreline polyline."""
    ys = np.linspace(-20, SIZE_MM + 20, 600)
    return polyline_distance(gx, gy, np.column_stack([river_centre(ys), ys]))


def smooth_ground(d: np.ndarray, gx: np.ndarray, gy: np.ndarray, hills: bool = True) -> np.ndarray:
    """Continuous valley surface (mm) before terracing: floodplain by the river, hills toward the rim."""
    rise = 12.5 * (1 - np.exp(-((np.maximum(d - CHANNEL_HALF_MM, 0)) / 58.0) ** 2))
    g = POOL_MM + STEP_MM + 0.3 + rise
    if hills:
        wobble = np.clip((d - 12) / 10, 0, 1)                 # keep the floodplain edge clean
        g = g + wobble * (0.9 * np.sin(gx / 8.5 + gy / 14.0) + 0.7 * np.cos(gy / 7.0 - gx / 19.0))
        fade = np.clip((d - 30) / 40, 0, 1)
        g = g + fade * (2.6 * np.sin(gx / 21.0 + 0.7) * np.cos(gy / 27.0) + 1.4 * np.sin((gx + gy) / 13.0))
    return g


def terrace(g: np.ndarray) -> np.ndarray:
    k = np.clip(np.floor((g - POOL_MM) / STEP_MM), 1, TOP_STEP)
    return POOL_MM + k * STEP_MM


def text_mask(text: str, cx: float, cy: float, cap_mm: float, gx: np.ndarray, gy: np.ndarray,
              rotate180: bool = False) -> np.ndarray:
    """Boolean mask of `text` centred at (cx, cy) with letters cap_mm tall, rasterised onto the grid."""
    from PIL import Image, ImageDraw, ImageFont

    px_per_mm = 12
    size_px = int(cap_mm * px_per_mm / 0.72)              # cap height is ~72% of the em
    font = next((ImageFont.truetype(f, size_px) for f in FONT_CANDIDATES if Path(f).exists()), None)
    font = font or ImageFont.load_default(size=size_px)
    left, top, right, bottom = font.getbbox(text)
    img = Image.new("L", (right - left + 4, bottom - top + 4), 0)
    ImageDraw.Draw(img).text((2 - left, 2 - top), text, fill=255, font=font)
    a = np.asarray(img) > 127
    h_px, w_px = a.shape
    u = (gx - cx) * px_per_mm + w_px / 2
    v = (cy - gy) * px_per_mm + h_px / 2                  # image rows go down, y goes north
    if rotate180:
        u, v = w_px - u, h_px - v
    inside = (u >= 0) & (u < w_px) & (v >= 0) & (v < h_px)
    out = np.zeros(gx.shape, bool)
    out[inside] = a[v[inside].astype(int), u[inside].astype(int)]
    return out


def box_mask(gx, gy, x0, y0, x1, y1):
    return (gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)


# ---------------------------------------------------------------- features
def add_road(h, gx, gy, d, feats):
    on = (np.abs(gy - ROAD_Y_MM) <= ROAD_HALF_MM) & (gx > RIM_MM) & (gx < SIZE_MM - RIM_MM)
    gs = smooth_ground(d, gx, gy, hills=False)
    surface = np.minimum(gs + ROAD_LIFT_MM, DECK_MM + ROAD_RAMP * d)
    h = np.where(on, surface, h)
    phase = np.mod(gx, DASH_MM + GAP_MM) < DASH_MM
    dash = on & phase & (np.abs(gy - ROAD_Y_MM) <= DASH_HALF_MM) & (d > CHANNEL_HALF_MM + 2)
    h = np.where(dash, h - DASH_DEPTH_MM, h)
    feats["road"] = {"y_mm": ROAD_Y_MM, "width_mm": 2 * ROAD_HALF_MM, "deck_mm": DECK_MM,
                     "crossing_x_mm": float(river_centre(np.array(ROAD_Y_MM)))}
    return h


def add_car(h, gx, gy, feats):
    """Stranded car on the east approach, nose toward the water."""
    cx = float(river_centre(np.array(ROAD_Y_MM))) + CHANNEL_HALF_MM + 6.5
    cy = ROAD_Y_MM - 1.8

    def rounded(hx, hy, p=4):
        return (np.abs(gx - cx - 0.0) / hx) ** p + (np.abs(gy - cy) / hy) ** p <= 1

    body = rounded(6.2, 2.9)
    base = float(h[body].max())
    h = np.where(body, base + 2.0, h)
    cab = (np.abs((gx - cx - 0.6) / 3.0) ** 4 + np.abs((gy - cy) / 2.3) ** 4) <= 1
    # windscreen slope on the side facing the water (west), flat roof behind it
    slope = np.clip((gx - (cx - 2.4)) / 1.2, 0, 1)
    h = np.where(cab, base + 2.0 + 1.4 * slope, h)
    feats["car"] = {"centre_mm": [cx, cy], "road_mm": round(base, 2), "body_top_mm": round(base + 2.0, 2),
                    "roof_mm": round(base + 3.4, 2)}
    return h


HOUSES = (  # (dx from river centre, y, angle-free footprint w x l, ridge along x?)
    (-20, 160, 9, 7, True), (-32, 150, 8, 7, False), (-21, 40, 9, 7, True), (-34, 55, 8, 8, False),
    (22, 165, 9, 7, True), (36, 52, 9, 7, False), (24, 70, 8, 7, True), (-48, 128, 9, 7, True),
    (58, 150, 9, 7, False), (-58, 90, 9, 7, True), (52, 34, 8, 7, True),
)


def add_houses(h, gx, gy, keepout, feats):
    out = []
    for dx, y, w, depth, ridge_x in HOUSES:
        x = float(river_centre(np.array(y))) + dx
        m = box_mask(gx, gy, x - w / 2, y - depth / 2, x + w / 2, y + depth / 2)
        if not m.any() or (m & keepout).any():
            continue
        base = float(h[m].max())
        eave = base + 2.4
        across = np.abs(gy - y) / (depth / 2) if ridge_x else np.abs(gx - x) / (w / 2)
        roof = eave + 1.6 * (1 - np.clip(across, 0, 1))
        h = np.where(m, roof, h)
        keepout = keepout | m
        out.append({"centre_mm": [round(x, 1), y], "ground_mm": base, "eave_mm": eave, "ridge_mm": eave + 1.6})
    feats["houses"] = out
    return h, keepout


def add_trees(h, gx, gy, d, keepout, feats, seed=7, count=70):
    rng = np.random.default_rng(seed)
    out = []
    tries = 0
    while len(out) < count and tries < 4000:
        tries += 1
        x, y = rng.uniform(RIM_MM + 4, SIZE_MM - RIM_MM - 4, 2)
        i, j = int(round(y / RES_MM)), int(round(x / RES_MM))
        if d[i, j] < 34 or keepout[i, j] or abs(y - ROAD_Y_MM) < ROAD_HALF_MM + 5:
            continue
        if any((x - a) ** 2 + (y - b) ** 2 < 6.0 ** 2 for a, b, _ in out):
            continue
        r = rng.uniform(2.2, 3.0)
        rr = np.hypot(gx - x, gy - y)
        m = rr <= r
        if (m & keepout).any():
            continue
        base = float(h[m].max())
        cone = base + rng.uniform(3.6, 5.0) * (1 - rr / r)
        h = np.where(m, np.maximum(h, cone), h)
        out.append((x, y, round(base, 2)))
    feats["trees"] = len(out)
    return h


def add_rim(h, gx, gy, feats):
    interior = box_mask(gx, gy, RIM_MM, RIM_MM, SIZE_MM - RIM_MM, SIZE_MM - RIM_MM)
    h = np.where(interior, h, RIM_TOP_MM)
    tags = []
    corners = [(PAD_MM / 2, PAD_MM / 2), (SIZE_MM - PAD_MM / 2, PAD_MM / 2),
               (SIZE_MM - PAD_MM / 2, SIZE_MM - PAD_MM / 2), (PAD_MM / 2, SIZE_MM - PAD_MM / 2)]
    for tid, (cx, cy) in zip(TAG_IDS, corners, strict=True):
        pad = box_mask(gx, gy, cx - PAD_MM / 2, cy - PAD_MM / 2, cx + PAD_MM / 2, cy + PAD_MM / 2)
        h = np.where(pad, RIM_TOP_MM, h)
        q = TAG_MM / 2 + 0.2
        h = np.where(box_mask(gx, gy, cx - q, cy - q, cx + q, cy + q), RIM_TOP_MM - TAG_RECESS_MM, h)
        z, t = RIM_TOP_MM - TAG_RECESS_MM, TAG_MM / 2
        tags.append({"id": tid, "centre_mm": [cx, cy, z],
                     "corners_mm": [[cx - t, cy + t, z], [cx + t, cy + t, z], [cx + t, cy - t, z], [cx - t, cy - t, z]]})
    mid = SIZE_MM / 2
    h = np.where(text_mask("FLOOD WATCH", mid, RIM_MM / 2, 5.6, gx, gy), RIM_TOP_MM + EMBOSS_MM, h)
    h = np.where(text_mask("GUADALUPE RIVER  KERRVILLE TX", mid, SIZE_MM - RIM_MM / 2, 4.4, gx, gy,
                           rotate180=True), RIM_TOP_MM + EMBOSS_MM, h)
    feats["fiducials"] = {"dictionary": "DICT_4X4_50", "tag_mm": TAG_MM, "pad_mm": PAD_MM, "tags": tags}
    return h


# ---------------------------------------------------------------- mesh
def heightfield_solid(h: np.ndarray, res: float) -> np.ndarray:
    """Closed solid: heightfield top, vertical walls, flat bottom at z = 0. Row 0 is the south edge."""
    ny, nx = h.shape
    gx, gy = np.meshgrid(np.arange(nx) * res, np.arange(ny) * res)
    top = np.stack([gx, gy, h], axis=-1)
    a, b, c, d = top[:-1, :-1], top[:-1, 1:], top[1:, 1:], top[1:, :-1]
    tris = [np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)]
    ring = np.concatenate([top[0, :-1], top[:-1, -1], top[-1, :0:-1], top[:0:-1, 0]])
    p, q = ring, np.roll(ring, -1, axis=0)
    pb, qb = p * [1, 1, 0], q * [1, 1, 0]
    tris += [np.stack([pb, qb, q], 1), np.stack([pb, q, p], 1)]
    centre = np.broadcast_to([gx.mean(), gy.mean(), 0.0], pb.shape)
    tris.append(np.stack([centre, qb, pb], 1))
    return np.concatenate(tris)


def is_watertight(tris: np.ndarray) -> bool:
    """Every directed edge appears once and its reverse appears once (closed, consistently wound)."""
    v = np.round(tris.reshape(-1, 3), 4)
    _, idx = np.unique(v, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3).astype(np.int64)
    n = idx.max() + 1
    e = np.concatenate([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]])
    fwd = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    uniq, counts = np.unique(fwd, return_counts=True)
    return bool((counts == 1).all() and np.isin(rev, uniq).all())


def write_stl(path: Path, tris: np.ndarray) -> None:
    tris = np.asarray(tris, dtype=np.float32)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    rec["n"], rec["v"] = n, tris
    with path.open("wb") as fh:
        fh.write(STL_HEADER)
        fh.write(np.uint32(len(tris)).tobytes())
        fh.write(rec.tobytes())


def volume_mm3(tris: np.ndarray) -> float:
    t = np.asarray(tris, dtype=float)
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def pour_table(h: np.ndarray, river: np.ndarray, res: float) -> list[dict]:
    """mL of water to bring the tray from empty to each step level (only water connected to the river)."""
    try:
        from scipy import ndimage
    except ImportError:
        ndimage = None
    cell = res * res
    rows = []
    for k in range(0, POUR_LEVELS + 1):
        level = POOL_MM + k * STEP_MM
        wet = h < level
        if ndimage is not None:
            lab, _ = ndimage.label(wet)
            keep = np.unique(lab[river & wet])
            wet = np.isin(lab, keep[keep > 0])
        ml = float(((level - h)[wet]).sum() * cell / 1000)
        rows.append({"ft": k, "level_mm": level, "ml": round(ml, 1), "wet_fraction": round(float(wet.mean()), 3)})
    return rows


# ---------------------------------------------------------------- build
def build_heightmap() -> tuple[np.ndarray, dict, np.ndarray]:
    n = int(round(SIZE_MM / RES_MM)) + 1
    gy, gx = np.mgrid[0:n, 0:n] * RES_MM
    d = river_distance(gx, gy)
    feats: dict = {}
    dc = polyline_distance(gx, gy, creek_line())
    valley = np.minimum(d, 1.7 * dc + 4.0)                 # creek valley: narrower, joins the river's
    h = terrace(smooth_ground(valley, gx, gy))
    creek = (dc < 2.6) & (d > CHANNEL_HALF_MM - 1)
    h = np.where(creek, POOL_MM - 1.0, h)
    river = d < CHANNEL_HALF_MM
    h = np.where(river, FLOOR_MM, h)
    feats["creek"] = {"bed_mm": POOL_MM - 1.0, "half_width_mm": 2.6}
    d = valley                                              # trees keep away from both waterways
    h = add_road(h, gx, gy, d, feats)
    h = add_car(h, gx, gy, feats)
    keepout = (np.abs(gy - ROAD_Y_MM) <= ROAD_HALF_MM + 1.5) | river
    h, keepout = add_houses(h, gx, gy, keepout, feats)
    h = add_trees(h, gx, gy, d, keepout, feats)
    h = add_rim(h, gx, gy, feats)
    return h, feats, river


XY_SCALARS = {"y_mm", "crossing_x_mm", "width_mm", "half_width_mm", "tag_mm", "pad_mm"}
XY_POINTS = {"centre_mm", "corners_mm", "x_mm", "y_mm"}       # [x, y(, z)] or [lo, hi] or lists of those


def _scale_points(v, s: float):
    if v and isinstance(v[0], list):
        return [_scale_points(p, s) for p in v]
    if len(v) == 3:
        return [v[0] * s, v[1] * s, v[2]]                     # z is a height: unchanged
    return [v[0] * s, v[1] * s]


def scale_xy(obj, s: float):
    """Scale horizontal positions/sizes in the feature dict by s; heights are left exact."""
    if isinstance(obj, list):
        return [scale_xy(v, s) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k in XY_POINTS and isinstance(v, list):
            out[k] = _scale_points(v, s)
        elif k in XY_SCALARS and isinstance(v, (int, float)):
            out[k] = v * s
        else:
            out[k] = scale_xy(v, s)
    return out


def build(out: Path = OUT, xy_scale: float = 1.0) -> dict:
    """xy_scale < 1 shrinks the footprint (faster print) but keeps every height, so steps stay STEP_MM."""
    out.mkdir(parents=True, exist_ok=True)
    h, feats, river = build_heightmap()
    res = RES_MM * xy_scale
    feats = scale_xy(feats, xy_scale) if xy_scale != 1.0 else feats
    tris = heightfield_solid(h, res)
    write_stl(out / "gauge_tray.stl", tris)
    tags = feats["fiducials"]["tags"]
    np.savez_compressed(out / "truth.npz", height_mm=h.astype(np.float32), river=river, res_mm=res,
                        pool_mm=POOL_MM, step_mm=STEP_MM,
                        fiducial_corners_mm=np.array([t["corners_mm"] for t in tags]), fiducial_ids=np.array(TAG_IDS))
    manifest = {
        "name": "FloodWatch gauge tray",
        "size_mm": [SIZE_MM * xy_scale, SIZE_MM * xy_scale, float(h.max())], "res_mm": res, "xy_scale": xy_scale,
        "triangles": len(tris), "watertight": is_watertight(tris), "volume_cm3": round(volume_mm3(tris) / 1000, 1),
        "levels": {"floor_mm": FLOOR_MM, "pool_mm": POOL_MM, "step_mm": STEP_MM, "step_means": "1 ft of rise",
                   "terraces_mm": [POOL_MM + k * STEP_MM for k in range(1, TOP_STEP + 1)], "rim_top_mm": RIM_TOP_MM},
        "pour_table": pour_table(h, river, res),
        **feats,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the one-piece FloodWatch gauge tray STL")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--xy-scale", type=float, default=1.0,
                    help="shrink the footprint for a faster print, e.g. 0.8 -> 160 mm (heights unchanged)")
    args = ap.parse_args()
    m = build(args.out, args.xy_scale)
    sx, sy, sz = m["size_mm"]
    print(f"Wrote {args.out}")
    print(f"  {sx:.0f} x {sy:.0f} x {sz:.1f} mm, {m['triangles']:,} triangles, watertight {m['watertight']}, "
          f"{m['volume_cm3']} cm3")
    print(f"  houses {len(m['houses'])}, trees {m['trees']}, car road {m['car']['road_mm']} mm")
    for row in m["pour_table"]:
        print(f"  {row['ft']:>2} ft  level {row['level_mm']:5.1f} mm  pour {row['ml']:6.1f} mL  wet {row['wet_fraction']:.0%}")


if __name__ == "__main__":
    main()
