"""Render the drone vision model over real flood footage: waterline, tracked vehicles/people, water-height key.

  uv run python -m vision.demo_video --clip ../data/demo_videos/raw/yt_tFCaJNsK3_8.mp4 --start 50 --dur 24 \
      --site ../data/demo_videos/dietert --out ../data/demo_videos/out/dietert.mp4

The water height in the key has one of two sources, always named in the key:
- MODEL (only with --site): the waterline in the frame is cast onto lidar terrain from a camera pose fitted to
  mapped landmarks (vision/georef.py) and tracked by rotation. CI95 and P(within +-1 ft) come from a Monte Carlo
  over the pose uncertainty plus lidar error. Ground-level views use the image-space waterline (one boundary
  pixel per column); the drone pipeline's ground-grid edge finder needs a high oblique view.
- GAUGE: USGS stage over the clip's time window (datum + stage, NAVD88). CI95 and P(+-1 ft) treat the capture
  time as uniform over the window.
Every number shown is computed; nothing is decorative.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from app.config import DATA_DIR
from vision.camera import Pose, ray_to_terrain
from vision.config import vision_config
from vision.gauge_range import M_PER_FT, GaugeSeries, epoch
from vision.grid import BLOCKER, GROUND, Seg

log = logging.getLogger("vision.demo_video")
CDT = timezone(timedelta(hours=-5))
HYDRO = DATA_DIR / "region" / "hill_country" / "hydrographs_2025-07-04.json"
MONO = "/System/Library/Fonts/Menlo.ttc"
M_TO_FT = 1 / M_PER_FT
FT = M_PER_FT
CYAN, AMBER, RED, GREY = (255, 220, 60), (40, 170, 255), (80, 80, 255), (200, 200, 200)   # BGR


# ---------------------------------------------------------------- waterline -> elevation (model)

def shoreline_pixels(seg: Seg, lut: np.ndarray, step: int = 12, min_row: int = 0) -> np.ndarray:
    """Per column, the lowest water pixel that sits directly above open ground (bottom-up scan)."""
    water = seg.p_water >= 0.5
    grp = lut[np.clip(seg.labels, 0, len(lut) - 1)]
    h, w = water.shape
    out = []
    for u in range(step // 2, w, step):
        col = water[:, u]
        for v in range(h - 7, max(min_row, 1), -1):
            if col[v] and not col[v + 1] and int((grp[v + 1:v + 6, u] == GROUND).sum()) >= 4:
                out.append((u + 0.5, v + 0.5))
                break
    return np.array(out, float).reshape(-1, 2)


def shoreline_z(cam, pose: Pose, px: np.ndarray, height_at) -> float | None:
    if len(px) < 8:
        return None
    pts, hit = ray_to_terrain(cam, pose, px, height_at, 400.0)
    return float(np.median(pts[hit, 2])) if hit.sum() >= 8 else None


def pose_samples(fit, px: np.ndarray, height_at, n: int = 120, seed: int = 0) -> np.ndarray:
    """Shoreline elevation offsets (m) from the best pose, over the pose uncertainty."""
    rng = np.random.default_rng(seed)
    p = fit.pose
    base = shoreline_z(fit.cam, p, px, height_at)
    out = []
    for _ in range(n):
        q = Pose(p.x + rng.normal(0, fit.sigma_m / 1.41), p.y + rng.normal(0, fit.sigma_m / 1.41),
                 p.z + rng.normal(0, fit.sigma_z_m), p.heading_deg + rng.normal(0, 1.5),
                 p.pitch_deg + rng.normal(0, fit.sigma_pitch_deg), p.roll_deg + rng.normal(0, 0.7))
        z = shoreline_z(fit.cam, q, px, height_at)
        if z is not None and base is not None:
            out.append(z - base)
    return np.array(out) if len(out) >= 20 else np.random.default_rng(1).normal(0, 0.5, 200)


@dataclass(frozen=True)
class WaterEstimate:
    best_ft: float
    lo_ft: float               # 95% interval
    hi_ft: float
    p_1ft: float               # probability the true level is within +-1 ft of best
    source: str                # short, e.g. "MODEL · waterline × lidar" or "USGS 08166140 · gauge"

    @staticmethod
    def from_samples(samples_ft: np.ndarray, source: str) -> "WaterEstimate":
        s = np.asarray(samples_ft, float)
        best = float(np.median(s))
        lo, hi = np.percentile(s, [2.5, 97.5])
        return WaterEstimate(best, float(lo), float(hi), float(np.mean(np.abs(s - best) <= 1.0)), source)


def gauge_estimate(gauge: GaugeSeries, window: tuple[float, float], source: str) -> WaterEstimate | None:
    ts = np.linspace(window[0], window[1], 400)
    st = [gauge.stage_at(t) for t in ts]
    st = np.array([s for s in st if s is not None])
    if len(st) == 0:
        return None
    return WaterEstimate.from_samples(gauge.datum_ft + st, source)


# ---------------------------------------------------------------- drawing

def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(MONO, size)
    except OSError:
        return ImageFont.load_default()


def _corners(img, box, col, t):
    x1, y1, x2, y2 = (int(round(c)) for c in box)
    L = max(8, int(0.22 * min(x2 - x1, y2 - y1)))
    for (x, y, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(img, (x, y), (x + dx * L, y), col, t, cv2.LINE_AA)
        cv2.line(img, (x, y), (x, y + dy * L), col, t, cv2.LINE_AA)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    cv2.line(img, (cx - 6, cy), (cx + 6, cy), col, 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 6), (cx, cy + 6), col, 1, cv2.LINE_AA)
    overlay = img.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), col, 1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)


def draw_waterline(img: np.ndarray, p_water: np.ndarray) -> None:
    """Thin dashed waterline (the water/ground boundary), no fill."""
    m = (p_water >= 0.5).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    h = img.shape[0]
    for c in contours:
        if cv2.contourArea(c) < 0.004 * m.size:
            continue
        pts = c[:, 0, :]
        for i in range(0, len(pts) - 6, 12):           # dash: 6 on, 6 off
            seg = pts[i:i + 6]
            if (seg[:, 1] < 3).any() or (seg[:, 1] > h - 3).any():
                continue
            cv2.polylines(img, [seg.reshape(-1, 1, 2)], False, CYAN, 2, cv2.LINE_AA)


@dataclass(frozen=True)
class Tag:
    box: tuple[float, float, float, float]
    lines: tuple[str, ...]
    color: tuple[int, int, int]


def render_frame(frame, p_water, tags: list[Tag], shore_px, est: WaterEstimate | None, telemetry: str,
                 credit: str, place: str, waterline: bool = True) -> np.ndarray:
    from PIL import Image, ImageDraw

    img = frame.copy()
    if waterline:
        draw_waterline(img, p_water)
    if shore_px is not None:
        for u, v in shore_px.astype(int):
            cv2.drawMarker(img, (u, v), CYAN, cv2.MARKER_TILTED_CROSS, 7, 1, cv2.LINE_AA)
    s = img.shape[1] / 1280 if img.shape[1] >= img.shape[0] else img.shape[1] / 720
    for t in tags:
        _corners(img, t.box, t.color, max(2, int(2 * s)))
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    lay = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f_sm, f_md, f_lg, f_xl = _font(int(13 * s)), _font(int(15 * s)), _font(int(17 * s)), _font(int(34 * s))
    W, H = pil.size
    # tags: monospace chips above each box
    for t in tags:
        x1, y1 = int(t.box[0]), int(t.box[1])
        widest = max(d.textlength(line, font=f_md) for line in t.lines) + int(12 * s)
        x1 = int(min(max(0, x1), W - widest))
        rgb = t.color[::-1]
        lh = int(19 * s)
        y = max(0, y1 - lh * len(t.lines) - int(4 * s))
        for i, line in enumerate(t.lines):
            tw = d.textlength(line, font=f_md)
            d.rectangle([x1, y + i * lh, x1 + tw + int(10 * s), y + (i + 1) * lh - 2], fill=(8, 12, 18, 190))
            d.rectangle([x1, y + i * lh, x1 + int(3 * s), y + (i + 1) * lh - 2], fill=(*rgb, 255))
            d.text((x1 + int(7 * s), y + i * lh + int(1 * s)), line, font=f_md, fill=(*rgb, 255))
    # telemetry strip (top-right)
    tw = d.textlength(telemetry, font=f_sm)
    d.rectangle([W - tw - int(22 * s), int(10 * s), W - int(10 * s), int(30 * s)], fill=(8, 12, 18, 150))
    d.text((W - tw - int(16 * s), int(13 * s)), telemetry, font=f_sm, fill=(170, 235, 255, 230))
    # water-height key (bottom-left)
    pad = int(14 * s)
    kx, kw = pad, int(330 * s)
    kh = int(122 * s)
    ky = H - kh - int(36 * s)
    d.rectangle([kx, ky, kx + kw, ky + kh], fill=(8, 12, 18, 200))
    d.rectangle([kx, ky, kx + int(4 * s), ky + kh], fill=(*CYAN[::-1], 255))
    d.line([kx + int(14 * s), ky + int(17 * s), kx + int(40 * s), ky + int(17 * s)], fill=(*CYAN[::-1], 255),
           width=max(2, int(3 * s)))
    d.text((kx + int(48 * s), ky + int(8 * s)), "WATER SURFACE", font=f_lg, fill=(220, 240, 250, 255))
    if est is None:
        d.text((kx + int(14 * s), ky + int(36 * s)), "--", font=f_xl, fill=(240, 240, 240, 255))
        d.text((kx + int(14 * s), ky + int(82 * s)), "no estimate", font=f_md, fill=(170, 180, 190, 255))
    else:
        d.text((kx + int(14 * s), ky + int(32 * s)), f"{est.best_ft:,.1f} ft", font=f_xl, fill=(245, 250, 255, 255))
        d.text((kx + int(14 * s) + d.textlength(f"{est.best_ft:,.1f} ft ", font=f_xl), ky + int(50 * s)), "NAVD88",
               font=f_sm, fill=(150, 170, 185, 255))
        conf_rgb = (90, 230, 140) if est.p_1ft >= 0.7 else (255, 200, 80) if est.p_1ft >= 0.35 else (255, 120, 100)
        d.text((kx + int(14 * s), ky + int(76 * s)), f"CI95 {est.lo_ft:,.1f}–{est.hi_ft:,.1f}", font=f_md,
               fill=(200, 215, 225, 255))
        ptxt = f"P(±1ft) {est.p_1ft:.2f}"
        d.text((kx + kw - d.textlength(ptxt, font=f_md) - int(10 * s), ky + int(76 * s)), ptxt, font=f_md,
               fill=(*conf_rgb, 255))
        d.text((kx + int(14 * s), ky + int(98 * s)), est.source, font=f_sm, fill=(150, 170, 185, 255))
    d.text((kx, ky - int(20 * s)), place, font=f_sm, fill=(230, 235, 240, 220))
    cw = d.textlength(credit, font=f_sm)
    d.text((W - cw - int(12 * s), H - int(22 * s)), credit, font=f_sm, fill=(210, 210, 210, 170))
    out = Image.alpha_composite(pil, lay).convert("RGB")
    return cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------- main loop

def _crop(frame: np.ndarray, spec: str | None) -> np.ndarray:
    if not spec:
        return frame
    x, y, w, h = (float(v) for v in spec.split(","))
    H, W = frame.shape[:2]
    return frame[int(y * H):int((y + h) * H), int(x * W):int((x + w) * W)]


def _plausible(d, shape) -> bool:
    """Drop YOLO's known flood-footage false positives: frame-sized boxes and low-confidence 'boats' on waves."""
    x1, y1, x2, y2 = d.box
    frac = (x2 - x1) * (y2 - y1) / float(shape[0] * shape[1])
    return frac < 0.2 and not (d.cls == "boat" and d.conf < 0.6)


def _tags(dets, vehicles, people, water: np.ndarray, ocfg) -> list[Tag]:
    from vision.objects import ring_water_fraction

    conf = {d.track_id: d.conf for d in dets}
    out = []
    for v in vehicles:
        ring = ring_water_fraction(v.box, water, float(ocfg["ring_expand"]))
        lines = [f"VEH-{v.track_id:02d}  {v.type.upper()}  {conf.get(v.track_id, 0):.2f}"]
        if v.in_water:
            lines.append(f"IN WATER  {ring:.2f}")
        out.append(Tag(v.box, tuple(lines), AMBER if v.in_water else CYAN))
    for p in people:
        label = {"on_vehicle": "ON VEHICLE", "in_water": "IN WATER"}.get(p.situation, "")
        lines = [f"PER-{p.track_id:02d}  PERSON  {conf.get(p.track_id, 0):.2f}"] + ([label] if label else [])
        out.append(Tag(p.box, tuple(lines), RED))
    return out


def render(args: argparse.Namespace) -> None:
    from vision.detect import Tracker
    from vision.pipeline import _objects
    from vision.segment import Segmenter, lut_from_names

    cfg = vision_config()
    lut = lut_from_names()
    cap = cv2.VideoCapture(str(args.clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000)
    stride = max(1, int(round(fps / args.proc_fps)))
    est = None
    if args.window and not args.site:
        a, b = args.window.split("/")
        g = GaugeSeries.load(Path(args.gauge_file) if args.gauge_file else HYDRO, args.gauge)
        est = gauge_estimate(g, (epoch(a), epoch(b)), f"USGS {args.gauge} · gauge, {args.gauge_note}".rstrip(", "))

    def prep(fr):
        fr = _crop(fr, args.crop)
        return cv2.resize(fr, (args.width, int(round(fr.shape[0] * args.width / fr.shape[1]) // 2 * 2)))

    site = fit = None
    offs = None
    if args.site:
        from vision.georef import fit_pose
        from vision.site import load_site

        site = load_site(Path(args.site))
        uv = [np.array(site.cfg["keyframe_curb_px"], float)]
        lines = [site.line_xy]
        if site.inner_xy is not None:
            uv.append(np.array(site.cfg["keyframe_inner_px"], float))
            lines.append(site.inner_xy)
        ok, frame0 = cap.read()
        cap.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000)
        frame0 = prep(frame0)
        fit = fit_pose(uv, lines, site.grid.height_at, (frame0.shape[1], frame0.shape[0]), (0.0, 0.0),
                       site.ground_z, site.priors)
        log.info("pose fit: rms %.1f px, pitch sigma %.2f deg, eye %.1f m", fit.rms_px, fit.sigma_pitch_deg,
                 fit.pose.z - site.ground_z)

    seg_model, tracker = Segmenter(), Tracker(min_frames=args.persist)
    tracker.img_size, tracker.conf = args.det_size, args.det_conf
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    enc, ema, prev_gray = None, None, None
    pose = fit.pose if fit else None
    z_hist: list[float] = []
    shore, tags, dets = None, [], []
    n_total = int(args.dur * fps)
    posters = sorted({int(n_total * f) for f in (0.2, 0.5, 0.8)})
    rng = np.random.default_rng(3)
    for k in range(n_total):
        ok, frame = cap.read()
        if not ok:
            break
        frame = prep(frame)
        if k % stride == 0:
            seg = seg_model.run(frame)
            ema = seg.p_water if ema is None or ema.shape != seg.p_water.shape else 0.5 * ema + 0.5 * seg.p_water
            seg = Seg(seg.labels, ema.astype(np.float32), seg.low_light, seg.zero_shot_frac)
            dets = [d for d in tracker.update(frame) if _plausible(d, frame.shape)]
            vehicles, people = _objects(dets, seg, None, None, cfg)
            tags = _tags(dets, vehicles, people, seg.p_water >= 0.5, cfg["objects"])
            if fit is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    from vision.georef import rotate_pose, track_rotation

                    grp = lut[np.clip(seg.labels, 0, len(lut) - 1)]
                    static = (seg.p_water < 0.3) & (grp != BLOCKER)
                    static[: int(0.35 * static.shape[0])] = False          # sky and wires
                    r_rel, n_in = track_rotation(prev_gray, gray, fit.cam, static)
                    if r_rel is not None and n_in >= 15:
                        pose = rotate_pose(pose, r_rel)
                prev_gray = gray
                shore = shoreline_pixels(seg, lut, min_row=int(0.45 * frame.shape[0]))
                z = shoreline_z(fit.cam, pose, shore, site.grid.height_at)
                if z is not None:
                    z_hist = (z_hist + [z])[-int(3 * args.proc_fps):]
                if offs is None and len(shore) >= 8:
                    offs = pose_samples(fit, shore, site.grid.height_at)
                if z_hist and offs is not None and (k % int(fps) == 0 or est is None):
                    zc = float(np.median(z_hist))
                    samples = zc + offs + rng.normal(0, 0.10, len(offs))       # + lidar vertical error
                    est = WaterEstimate.from_samples(samples * M_TO_FT, "MODEL · waterline × 1 m lidar")
        trk = len(tags)
        telemetry = (f"FLOODWATCH//VISION  SEG segformer-b0+clipseg  DET yolov8n·bytetrack  "
                     f"T+{k / fps:05.1f}s  TRK {trk}")
        img = render_frame(frame, ema, tags, shore if fit is not None else None, est, telemetry, args.credit,
                           args.place, waterline=not args.no_waterline)
        if enc is None:
            h, w = img.shape[:2]
            enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                    "-s", f"{w}x{h}", "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264",
                                    "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "veryfast", str(out_path)],
                                   stdin=subprocess.PIPE)
        enc.stdin.write(img.tobytes())
        if k in posters:
            cv2.imwrite(str(out_path.with_name(f"{out_path.stem}_poster{posters.index(k) + 1}.jpg")), img)
    cap.release()
    if enc is not None:
        enc.stdin.close()
        enc.wait()
    log.info("wrote %s (water %s)", out_path, None if est is None else f"{est.best_ft:.1f} ft p1={est.p_1ft:.2f}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=20.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--site", default=None, help="georeferenced site folder (site.json, dem1m.npz, osm.geojson)")
    ap.add_argument("--window", default=None, help="gauge time window ISO/ISO, e.g. 2025-07-04T06:30-05:00/...")
    ap.add_argument("--gauge", default="08166200")
    ap.add_argument("--gauge-file", default=None, help="hydrograph JSON (default: the July 2025 replay file)")
    ap.add_argument("--gauge-note", default="")
    ap.add_argument("--place", default="")
    ap.add_argument("--credit", default="")
    ap.add_argument("--crop", default=None, help="x,y,w,h fractions (cut broadcast graphics)")
    ap.add_argument("--proc-fps", type=float, default=6.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--det-size", type=int, default=1280)
    ap.add_argument("--det-conf", type=float, default=0.3)
    ap.add_argument("--no-waterline", action="store_true", help="hide the waterline (e.g. unreliable at night)")
    ap.add_argument("--persist", type=int, default=3, help="frames a track must persist before it is drawn")
    render(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
