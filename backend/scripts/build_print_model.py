"""Build the 3D-printable downtown Kerrville flood tray and its CAD ground truth.

    cd backend && uv run python -m scripts.build_print_model

Source: the cached 10 m USGS 3DEP DEM (data/town/dem10.npz), OSM roads and river (data/town/), building
centroids (data/region/hill_country/places.json). Writes data/print_model/:
  terrain.stl         the tray: terrain + carved Guadalupe channel + rim walls + 4 fiducial pads (one body)
  roads.stl           road ribbons 0.4 mm proud of the terrain (second colour)
  buildings.stl       building blocks (third colour)
  terrain_lowpoly.stl the tray decimated (step 4, ~29k triangles) for Fusion mesh -> BRep
  truth.npz           merged heightmap (mm) the camera sees, world DEM, river mask, scale, fiducial corners
  volume_curve.json   pour table: water level mm <-> mL <-> world rise m
  manifest.json       parameters, critical point, road polylines (model mm), fiducial layout
  fiducials_print.png ArUco tags at exact size (print at 300 dpi, 100 % scale)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math

import cv2
import numpy as np
from pyproj import Transformer
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import shape

from app.config import DATA_DIR
from scripts.build_wx_flood import DEM_PATH, load_dem, town_bounds
from sim.print_mesh import box, heightfield_solid, is_watertight, ribbon, volume_mm3, write_stl
from sim.print_scale import PrintScale, volume_curve

OUT = DATA_DIR / "print_model"
TOWN = DATA_DIR / "town"
REGION = DATA_DIR / "region" / "hill_country"

CENTRE_LONLAT = (-99.1375, 30.0415)    # Sidney Baker bridge (cp-0154) to the Quinlan Creek crossings
CROP_M = 1200.0
MAP_MM = 220.0
EXAGGERATION = 3.0
RES_MM = 0.5
BASE_MM = 4.0
RIM_MM = 8.0
PAD_MM = 24.0                           # square corner pads, flush with the rim top
TAG_MM = 20.0
RIM_ABOVE_MM = 3.0
SMOOTH_CELLS = 1.0
RIVER_HALF_WIDTH_M = 18.0
CHANNEL_DEPTH_M = 1.0                   # channel floor below the low-flow surface (holds water at rise 0)
ROAD_HALF_WIDTH_MM = 0.75               # 1.5 mm printed road (8 m at scale; real roads are ~8-10 m)
ROAD_LIFT_MM, ROAD_SINK_MM = 0.4, 0.3
BLDG_MIN_MM, BLDG_HEIGHT_MM, BLDG_SINK_MM = 1.2, 1.5, 0.3
LOWPOLY_STEP = 3                        # minimum; the build uses the next step that divides the grid
LEVEL_STEP_MM = 0.1
TAG_DICT = "DICT_4X4_50"
TAG_IDS = (0, 1, 2, 3)                  # SW, SE, NE, NW
STATIONS = ("cp-0154", "cp-0043")       # Sidney Baker bridge (Guadalupe edge, every level); Park St crossing (~9 m)
STATION_ROAD_SEARCH_MM = 15.0


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def world_grid(scale: PrintScale, crop_m: float) -> tuple[np.ndarray, np.ndarray, Transformer, tuple[float, float]]:
    """Cell-centre UTM coordinates of the map area, row 0 south."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    cx, cy = to_utm.transform(*CENTRE_LONLAT)
    n = int(round(MAP_MM / RES_MM)) + 1
    off = np.arange(n) * RES_MM / scale.mm_per_m - crop_m / 2
    return cx + off, cy + off, to_utm, (cx, cy)


def sample_dem(ux: np.ndarray, uy: np.ndarray) -> np.ndarray:
    z, lon, lat = load_dem(town_bounds())                  # rows north -> south
    interp = RegularGridInterpolator((lat[::-1], lon), z[::-1], bounds_error=True)
    to_ll = Transformer.from_crs("EPSG:32614", "EPSG:4326", always_xy=True)
    gx, gy = np.meshgrid(ux, uy)
    glon, glat = to_ll.transform(gx, gy)
    out = interp(np.column_stack([glat.ravel(), glon.ravel()])).reshape(gx.shape)
    if np.isnan(out).any():
        raise ValueError("DEM has no-data inside the crop; move CENTRE_LONLAT")
    return out


def features_of(path) -> list[dict]:
    gj = json.loads(path.read_text())
    return gj["features"] if gj.get("type") == "FeatureCollection" else [gj]


def lines_local(features, to_utm: Transformer, origin: tuple[float, float]) -> list[np.ndarray]:
    """GeoJSON line features -> polylines in world metres relative to the crop centre."""
    out = []
    for f in features:
        geom = shape(f["geometry"])
        for g in getattr(geom, "geoms", [geom]):
            lon, lat = np.asarray(g.coords).T[:2]
            x, y = to_utm.transform(lon, lat)
            out.append(np.column_stack([np.asarray(x) - origin[0], np.asarray(y) - origin[1]]))
    return out


def clip_lines(lines: list[np.ndarray], half: float, step: float) -> list[np.ndarray]:
    """Densify every polyline to `step` and split it where it leaves the square |x|,|y| <= half."""
    out = []
    for ln in lines:
        seg_len = np.linalg.norm(np.diff(ln, axis=0), axis=1)
        dist = np.concatenate([[0], np.cumsum(seg_len)])
        if dist[-1] <= 0:
            continue
        s = np.linspace(0, dist[-1], max(2, int(dist[-1] / step) + 1))
        pts = np.column_stack([np.interp(s, dist, ln[:, 0]), np.interp(s, dist, ln[:, 1])])
        inside = np.all(np.abs(pts) <= half, axis=1)
        runs = np.split(np.arange(len(pts)), np.nonzero(np.diff(inside.astype(int)))[0] + 1)
        out += [pts[r] for r in runs if inside[r[0]] and len(r) >= 2]
    return out


def raster_mask(lines: list[np.ndarray], half_width: float, x0: float, y0: float, res: float,
                shape_: tuple[int, int]) -> np.ndarray:
    hit = np.zeros(shape_, dtype=bool)
    for ln in lines:
        j = np.clip(np.round((ln[:, 0] - x0) / res).astype(int), 0, shape_[1] - 1)
        i = np.clip(np.round((ln[:, 1] - y0) / res).astype(int), 0, shape_[0] - 1)
        hit[i, j] = True
    return ndimage.distance_transform_edt(~hit) * res <= half_width


def buildings_local(to_utm: Transformer, origin: tuple[float, float], half: float) -> list[tuple[float, float, float]]:
    """(x, y, side) in world metres for building centroids inside the crop."""
    rows = json.loads((REGION / "places.json").read_text())["buildings"]
    lon, lat, area = (np.array([r[k] for r in rows], dtype=float) for k in range(3))
    x, y = to_utm.transform(lon, lat)
    x, y = np.asarray(x) - origin[0], np.asarray(y) - origin[1]
    keep = (np.abs(x) < half) & (np.abs(y) < half)
    return [(float(a), float(b), float(math.sqrt(c))) for a, b, c in zip(x[keep], y[keep], area[keep])]


def stations(to_utm: Transformer, origin: tuple[float, float], model_xy, road_mm: list[np.ndarray]) -> list[dict]:
    """Measurement stations (critical points) with the nearest printed road as the depth reference."""
    pts = {q["id"]: q for q in json.loads((REGION / "nodes.json").read_text())["points"]}
    out = []
    for pid in STATIONS:
        p = pts[pid]
        x, y = to_utm.transform(p["lon"], p["lat"])
        xy = model_xy(np.array([x - origin[0], y - origin[1]]))
        near = [ln for ln in road_mm if float(np.min(np.linalg.norm(ln - xy, axis=1))) <= STATION_ROAD_SEARCH_MM]
        road = min(near, key=lambda ln: float(np.min(np.linalg.norm(ln - xy, axis=1)))) if near else None
        out.append({"id": pid, "kind": p["kind"], "name": p.get("name", ""), "lon": p["lon"], "lat": p["lat"],
                    "model_mm": xy.round(3).tolist(), "road_mm": None if road is None else road.round(3).tolist()})
    return out


def drop_on_mask(lines: list[np.ndarray], mask: np.ndarray, res: float) -> list[np.ndarray]:
    """Split polylines where they cross mask cells (bridges over the carved channel are not printed)."""
    out = []
    for ln in lines:
        i = np.clip(np.round(ln[:, 1] / res).astype(int), 0, mask.shape[0] - 1)
        j = np.clip(np.round(ln[:, 0] / res).astype(int), 0, mask.shape[1] - 1)
        keep = ~mask[i, j]
        runs = np.split(np.arange(len(ln)), np.nonzero(np.diff(keep.astype(int)))[0] + 1)
        out += [ln[r] for r in runs if keep[r[0]] and len(r) >= 2]
    return out


def fiducials(total_mm: float, z_mm: float) -> list[dict]:
    """Tag corners in model mm, ArUco order TL, TR, BR, BL with the tag's top edge facing north."""
    c = PAD_MM / 2
    centres = [(c, c), (total_mm - c, c), (total_mm - c, total_mm - c), (c, total_mm - c)]
    t = TAG_MM / 2
    return [{"id": tid, "centre_mm": [cx, cy, z_mm],
             "corners_mm": [[cx - t, cy + t, z_mm], [cx + t, cy + t, z_mm], [cx + t, cy - t, z_mm], [cx - t, cy - t, z_mm]]}
            for tid, (cx, cy) in zip(TAG_IDS, centres)]


def tag_sheet(path) -> None:
    dpi = 300
    px = int(round(TAG_MM / 25.4 * dpi))
    margin = int(round(6 / 25.4 * dpi))
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, TAG_DICT))
    sheet = np.full((2 * px + 3 * margin, 2 * px + 3 * margin), 255, np.uint8)
    for k, tid in enumerate(TAG_IDS):
        r, c = divmod(k, 2)
        y, x = margin + r * (px + margin), margin + c * (px + margin)
        sheet[y:y + px, x:x + px] = cv2.aruco.generateImageMarker(d, tid, px)
        cv2.putText(sheet, f"id {tid}  {TAG_MM:.0f} mm", (x, y + px + margin // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
    cv2.imwrite(str(path), sheet)


def build(crop_m: float = CROP_M, exaggeration: float = EXAGGERATION) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    mm_per_m = MAP_MM / crop_m
    ux, uy, to_utm, origin = world_grid(PrintScale(mm_per_m, exaggeration, 0.0, BASE_MM), crop_m)
    world = ndimage.gaussian_filter(sample_dem(ux, uy), SMOOTH_CELLS)
    res_m = RES_MM / mm_per_m
    half = crop_m / 2
    lx0 = ly0 = -half
    river_lines = clip_lines(lines_local(features_of(TOWN / "river.geojson"), to_utm, origin),
                             half, res_m / 2)
    river = raster_mask(river_lines, RIVER_HALF_WIDTH_M, lx0, ly0, res_m, world.shape)
    zref = float(np.percentile(world[river], 20))           # low-flow surface; tray water is level
    world = np.where(river, np.minimum(world, zref - CHANNEL_DEPTH_M), world)
    scale = PrintScale(mm_per_m, exaggeration, float(world.min()), BASE_MM)

    terrain_mm = scale.model_mm(world)
    rim_top = float(terrain_mm.max()) + RIM_ABOVE_MM + ROAD_LIFT_MM + BLDG_HEIGHT_MM
    pad = int(round(RIM_MM / RES_MM))
    tray = np.pad(terrain_mm, pad, constant_values=rim_top)
    total_mm = (tray.shape[1] - 1) * RES_MM
    corner = int(round(PAD_MM / RES_MM))
    for sl in ((slice(0, corner), slice(0, corner)), (slice(0, corner), slice(-corner, None)),
               (slice(-corner, None), slice(0, corner)), (slice(-corner, None), slice(-corner, None))):
        tray[sl] = rim_top
    map_x0 = RIM_MM                                         # model mm of the first map cell

    def model_xy(p: np.ndarray) -> np.ndarray:
        return (p + half) * mm_per_m + map_x0

    def tray_height(x, y):
        fj, fi = np.asarray(x) / RES_MM, np.asarray(y) / RES_MM
        return ndimage.map_coordinates(tray, [fi, fj], order=1, mode="nearest")

    road_lines = clip_lines(lines_local(features_of(TOWN / "segments.geojson"), to_utm, origin),
                            half - 2 * RIM_MM / mm_per_m, RES_MM / mm_per_m * 2)
    river_tray = np.pad(river, pad, constant_values=False)
    bridge_clear = ndimage.binary_dilation(river_tray, iterations=2)
    road_mm = drop_on_mask([model_xy(ln) for ln in road_lines], bridge_clear, RES_MM)
    road_tris = [t for t in (ribbon(ln, ROAD_HALF_WIDTH_MM, tray_height, ROAD_LIFT_MM, ROAD_SINK_MM) for ln in road_mm)
                 if t is not None]
    bldgs = buildings_local(to_utm, origin, half - 2 * RIM_MM / mm_per_m)

    # the heightmap the camera sees: terrain + road surface + building roofs (the vision ground truth)
    seen = tray.copy()
    gy, gx = np.mgrid[0:tray.shape[0], 0:tray.shape[1]] * RES_MM
    road_mask = raster_mask(road_mm, ROAD_HALF_WIDTH_MM, 0.0, 0.0, RES_MM, tray.shape)
    seen = np.where(road_mask, tray + ROAD_LIFT_MM, seen)
    bldg_tris = []
    for bx, by, side_m in bldgs:
        cx, cy = model_xy(np.array([bx, by]))
        s = max(side_m * mm_per_m, BLDG_MIN_MM) / 2
        inside = (np.abs(gx - cx) <= s) & (np.abs(gy - cy) <= s)
        if not inside.any():
            continue
        roof = float(tray[inside].max()) + BLDG_HEIGHT_MM
        seen = np.where(inside, np.maximum(seen, roof), seen)
        bldg_tris.append(box(cx - s, cy - s, cx + s, cy + s, float(tray[inside].min()) - BLDG_SINK_MM, roof))

    terrain_tris = heightfield_solid(tray, 0.0, 0.0, RES_MM)
    step = next(k for k in range(LOWPOLY_STEP, tray.shape[0]) if (tray.shape[0] - 1) % k == 0)  # keep the edges
    lowpoly = heightfield_solid(tray[::step, ::step], 0.0, 0.0, RES_MM * step)
    roads_all = np.concatenate(road_tris) if road_tris else np.zeros((0, 3, 3))
    bldg_all = np.concatenate(bldg_tris) if bldg_tris else np.zeros((0, 3, 3))
    for name, tris in (("terrain.stl", terrain_tris), ("terrain_lowpoly.stl", lowpoly),
                       ("roads.stl", roads_all), ("buildings.stl", bldg_all)):
        write_stl(OUT / name, tris)

    levels = np.arange(scale.model_mm(zref - CHANNEL_DEPTH_M), rim_top - 1.0, LEVEL_STEP_MM)
    curve = volume_curve(seen, levels, river_tray, RES_MM)
    fid = fiducials(total_mm, rim_top)
    sts = stations(to_utm, origin, model_xy, road_mm)
    np.savez_compressed(
        OUT / "truth.npz", height_mm=seen.astype(np.float32), terrain_mm=tray.astype(np.float32),
        world_m=world.astype(np.float32), river=river_tray, res_mm=RES_MM, map_x0_mm=map_x0,
        mm_per_m=mm_per_m, exaggeration=exaggeration, z_datum_m=scale.z_datum_m, base_mm=BASE_MM, zref_m=zref,
        fiducial_corners_mm=np.array([f["corners_mm"] for f in fid]), fiducial_ids=np.array(TAG_IDS),
    )
    table = [{"level_mm": round(lv, 3), "ml": round(ml, 2), "rise_m": round(scale.rise_m(lv, zref), 2)}
             for lv, ml in curve]
    (OUT / "volume_curve.json").write_text(json.dumps(table, indent=1))
    tag_sheet(OUT / "fiducials_print.png")

    manifest = {
        "region": "Downtown Kerrville, Guadalupe River + Quinlan Creek",
        "centre_lonlat": CENTRE_LONLAT, "utm_epsg": 32614, "utm_centre": origin, "crop_m": crop_m,
        "scale": {"mm_per_m": mm_per_m, "ratio": f"1:{1000 / mm_per_m:.0f}", "exaggeration": exaggeration,
                  "vertical_mm_per_m": scale.vertical_mm_per_m, "z_datum_m": scale.z_datum_m, "base_mm": BASE_MM},
        "zref_m": zref, "channel_floor_mm": float(scale.model_mm(zref - CHANNEL_DEPTH_M)),
        "zref_level_mm": float(scale.model_mm(zref)),
        "size_mm": [total_mm, total_mm, rim_top], "rim_mm": RIM_MM, "rim_top_mm": rim_top, "res_mm": RES_MM,
        "map_origin_mm": [map_x0, map_x0],
        "relief_m": [float(world.min()), float(world.max())],
        "counts": {"roads": len(road_tris), "buildings": len(bldg_tris),
                   "triangles": {"terrain": len(terrain_tris), "lowpoly": len(lowpoly),
                                 "roads": len(roads_all), "buildings": len(bldg_all)}},
        "watertight": {"terrain": is_watertight(terrain_tris), "lowpoly": is_watertight(lowpoly)},
        "volume_cm3": {"terrain": volume_mm3(terrain_tris) / 1000},
        "max_pour_ml": table[-1]["ml"], "max_rise_m": table[-1]["rise_m"],
        "stations": sts,
        "road_half_width_mm": ROAD_HALF_WIDTH_MM, "road_lift_mm": ROAD_LIFT_MM,
        "fiducials": {"dictionary": TAG_DICT, "tag_mm": TAG_MM, "pad_mm": PAD_MM, "tags": fid},
        "sources": {"dem10.npz": _sha(DEM_PATH), "segments.geojson": _sha(TOWN / "segments.geojson"),
                    "river.geojson": _sha(TOWN / "river.geojson"), "places.json": _sha(REGION / "places.json")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the 3D-printable Kerrville flood tray")
    ap.add_argument("--crop-m", type=float, default=CROP_M, help="world metres across the map (default 1200)")
    ap.add_argument("--exaggeration", type=float, default=EXAGGERATION, help="vertical exaggeration (default 3)")
    args = ap.parse_args()
    m = build(args.crop_m, args.exaggeration)
    s = m["scale"]
    print(f"Wrote {OUT}")
    print(f"  size {m['size_mm'][0]:.1f} x {m['size_mm'][1]:.1f} x {m['size_mm'][2]:.1f} mm, scale {s['ratio']}, "
          f"{s['exaggeration']}x vertical ({s['vertical_mm_per_m']:.3f} mm per world m)")
    print(f"  relief {m['relief_m'][0]:.1f}-{m['relief_m'][1]:.1f} m, low flow {m['zref_m']:.2f} m "
          f"= {m['zref_level_mm']:.2f} mm on the print")
    print(f"  roads {m['counts']['roads']}, buildings {m['counts']['buildings']}, watertight {m['watertight']}")
    print(f"  pour table to {m['max_rise_m']} m rise = {m['max_pour_ml']} mL")
    for st in m["stations"]:
        print(f"  station {st['id']} {st['kind']} {st['name']}: road {'yes' if st['road_mm'] else 'none'}")


if __name__ == "__main__":
    main()
