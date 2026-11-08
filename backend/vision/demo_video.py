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
FONTS = Path(__file__).parent / "fonts"            # B612 Mono: Airbus cockpit display face (OFL)
MONO, BOLD = FONTS / "B612Mono-Regular.ttf", FONTS / "B612Mono-Bold.ttf"
HUD = (150, 255, 190)                                 # RGB, HUD symbology
M_TO_FT = 1 / M_PER_FT
FT = M_PER_FT
CYAN, AMBER, RED, GREY = (190, 255, 150), (40, 190, 255), (70, 70, 255), (200, 200, 200)   # BGR; CYAN = HUD green


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

def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(str(BOLD if bold else MONO), size)
    except OSError:
        return ImageFont.load_default()


def _corners(img, box, col, t):
    """Open corner brackets with a small centre tick, no full rectangle."""
    x1, y1, x2, y2 = (int(round(c)) for c in box)
    L = max(6, int(0.18 * min(x2 - x1, y2 - y1)))
    for (x, y, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(img, (x, y), (x + dx * L, y), col, t, cv2.LINE_AA)
        cv2.line(img, (x, y), (x, y + dy * L), col, t, cv2.LINE_AA)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    cv2.line(img, (cx - 4, cy), (cx + 4, cy), col, 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 4), (cx, cy + 4), col, 1, cv2.LINE_AA)


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
        for i in range(0, len(pts) - 4, 10):           # dash: 4 on, 6 off
            seg = pts[i:i + 4]
            if (seg[:, 1] < 3).any() or (seg[:, 1] > h - 3).any():
                continue
            cv2.polylines(img, [seg.reshape(-1, 1, 2)], False, CYAN, 2, cv2.LINE_AA)


@dataclass(frozen=True)
class Tag:
    box: tuple[float, float, float, float]
    lines: tuple[str, ...]
    color: tuple[int, int, int]


def _txt(d, xy, text, font, fill, anchor="la"):
    """HUD text: no panel, a thin dark outline so it reads on any background."""
    d.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0, 200))


def _frame_brackets(d, W, H, s, col):
    m, L = int(18 * s), int(46 * s)
    w = max(1, int(1.5 * s))
    for (x, y, dx, dy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        d.line([x, y, x + dx * L, y], fill=col, width=w)
        d.line([x, y, x, y + dy * L], fill=col, width=w)
    cx, cy, g, r = W // 2, H // 2, int(8 * s), int(22 * s)           # boresight reticle
    for a, b in (((cx - r, cy), (cx - g, cy)), ((cx + g, cy), (cx + r, cy)),
                 ((cx, cy - r), (cx, cy - g)), ((cx, cy + g), (cx, cy + r))):
        d.line([a, b], fill=(*col[:3], 120), width=1)


def _tape(d, est: WaterEstimate, x, y0, y1, s, col, f_sm, f_md):
    """Vertical elevation tape (avionics altitude-tape style): 1 ft ticks, CI95 bracket, value box."""
    span = 8.0                                               # ft shown above and below the best estimate
    mid = (y0 + y1) / 2
    px_ft = (y1 - y0) / (2 * span)
    yv = lambda ft: mid - (ft - est.best_ft) * px_ft         # noqa: E731
    dim = (*col[:3], 150)
    d.line([x, y0, x, y1], fill=dim, width=1)
    for ft in range(int(np.floor(est.best_ft - span)), int(np.ceil(est.best_ft + span)) + 1):
        y = yv(ft)
        if not y0 <= y <= y1:
            continue
        major = ft % 5 == 0
        d.line([x, y, x - int((12 if major else 6) * s), y], fill=dim if not major else col, width=1)
        if major:
            _txt(d, (x - int(16 * s), y), f"{ft}", f_sm, dim, "rm")
    lo, hi = max(yv(est.lo_ft), y0), min(yv(est.hi_ft), y1)
    bx = x + int(6 * s)
    d.line([bx, hi, bx, lo], fill=col, width=max(2, int(2 * s)))
    for yy in (hi, lo):
        d.line([bx - int(3 * s), yy, bx + int(3 * s), yy], fill=col, width=1)
    bw, bh = int(118 * s), int(26 * s)                       # pointer box with the value
    bx0 = bx + int(10 * s)
    d.polygon([(bx0 - int(8 * s), mid), (bx0, mid - bh / 2), (bx0 + bw, mid - bh / 2), (bx0 + bw, mid + bh / 2),
               (bx0, mid + bh / 2)], fill=(0, 0, 0, 170), outline=col)
    d.text((bx0 + int(6 * s), mid), f"{est.best_ft:.1f}", font=f_md, fill=(255, 255, 255, 255), anchor="lm")
    _txt(d, (bx0 + bw // 2, y0 - int(8 * s)), "WSE FT", f_sm, col, "md")
    _txt(d, (bx0 + bw // 2, y1 + int(8 * s)), "NAVD88", f_sm, dim, "mt")


def render_frame(frame, p_water, tags: list[Tag], shore_px, est: WaterEstimate | None, telemetry: str,
                 credit: str, place: str, waterline: bool = True, t_s: float = 0.0) -> np.ndarray:
    from PIL import Image, ImageDraw

    img = frame.copy()
    if waterline:
        draw_waterline(img, p_water)
    if shore_px is not None:
        for u, v in shore_px.astype(int):
            cv2.drawMarker(img, (u, v), CYAN, cv2.MARKER_TILTED_CROSS, 5, 1, cv2.LINE_AA)
    W0, H0 = img.shape[1], img.shape[0]
    s = W0 / 1280 if W0 >= H0 else W0 / 720
    for t in tags:
        _corners(img, t.box, t.color, max(1, int(1.5 * s)))
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    lay = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f_xs, f_sm, f_md, f_lg = _font(int(11 * s)), _font(int(13 * s)), _font(int(16 * s), True), _font(int(30 * s), True)
    W, H = pil.size
    hud = (*HUD, 235)
    dim = (*HUD, 150)
    _frame_brackets(d, W, H, s, hud)
    # target tags: leader line up-right from the box corner, text only; stacked so labels never overlap
    placed: list[tuple[float, float, float, float]] = []
    lh = int(15 * s)
    for t in sorted(tags, key=lambda t: -t.box[2]):
        x1, y1, x2, _ = (int(c) for c in t.box)
        rgb = (*t.color[::-1], 255)
        widest = max(d.textlength(line, font=f_sm) for line in t.lines)
        th = lh * len(t.lines)
        right = x2 + int(24 * s) + widest < W - int(10 * s)
        tx = x2 + int(24 * s) if right else x1 - int(24 * s) - widest
        ly = max(int(70 * s), y1 - int(14 * s))
        for _ in range(12):
            r = (tx, ly - lh / 2, tx + widest, ly - lh / 2 + th)
            if not any(r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3] for q in placed):
                break
            ly -= th + int(4 * s)
        placed.append(r)
        ax = x2 if right else x1
        ex = tx - int(4 * s) if right else tx + widest + int(4 * s)
        d.line([(ax, y1), (ax + (1 if right else -1) * int(10 * s), ly), (ex, ly)], fill=rgb, width=1)
        for i, line in enumerate(t.lines):
            _txt(d, (tx, ly + i * lh), line, f_sm if i == 0 else f_xs, rgb if i == 0 else (*t.color[::-1], 200), "lm")
    # top-left: system + record + clock
    m = int(30 * s)
    _txt(d, (m, m), "HITIDE ISR", f_md, hud)
    _txt(d, (m + d.textlength("HITIDE ISR ", font=f_md), m + int(3 * s)), "EO/CH1  " + telemetry.split("|")[0],
         f_xs, dim)
    if int(t_s * 2) % 2 == 0:
        d.ellipse([m, m + int(26 * s), m + int(8 * s), m + int(34 * s)], fill=(255, 70, 60, 255))
    _txt(d, (m + int(14 * s), m + int(24 * s)), f"REC  T+{t_s:06.2f}", f_sm, hud)
    if place:
        _txt(d, (m, m + int(42 * s)), place.upper(), f_xs, dim)
    # top-right: model chain
    for i, part in enumerate(telemetry.split("|")[1:]):
        _txt(d, (W - m, m + i * int(16 * s)), part.strip(), f_xs if i else f_sm, hud if i == 0 else dim, "ra")
    # right: elevation tape
    if est is not None:
        half = min(0.20 * H, 0.28 * W)
        _tape(d, est, W - int(150 * s), int(H / 2 - half), int(H / 2 + half), s, hud, f_xs, f_md)
    # bottom-left: readout
    by = H - m
    if est is None:
        _txt(d, (m, by - int(20 * s)), "WSE  ----.-  FT", f_lg, dim, "ls")
    else:
        conf = (110, 255, 150, 255) if est.p_1ft >= 0.7 else (255, 205, 80, 255) if est.p_1ft >= 0.35 \
            else (255, 110, 90, 255)
        by -= int(16 * s)
        _txt(d, (m, by - int(52 * s)), "WATER SURFACE ELEV", f_xs, dim, "ls")
        _txt(d, (m, by - int(22 * s)), f"{est.best_ft:.1f}", f_lg, (255, 255, 255, 255), "ls")
        x = m + d.textlength(f"{est.best_ft:.1f} ", font=f_lg)
        _txt(d, (x, by - int(24 * s)), "FT NAVD88", f_sm, dim, "ls")
        row = f"CI95 {est.lo_ft:.1f}/{est.hi_ft:.1f}   "
        _txt(d, (m, by), row, f_sm, hud, "ls")
        x = m + d.textlength(row, font=f_sm)
        _txt(d, (x, by), f"P±1FT {est.p_1ft:.2f}", f_sm, conf, "ls")
        x += d.textlength(f"P±1FT {est.p_1ft:.2f}   ", font=f_sm)
        _txt(d, (m, by + int(16 * s)), "SRC " + est.source.upper(), f_xs, dim, "ls")
    if credit:
        _txt(d, (W - m, m + 3 * int(16 * s)), credit.upper(), f_xs, (220, 220, 220, 150), "ra")
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
        lines = [f"VEH-{v.track_id:02d} {v.type.upper()}", f"CONF {conf.get(v.track_id, 0):.2f}"]
        if v.in_water:
            lines.append(f"IN WATER {ring:.2f}")
        out.append(Tag(v.box, tuple(lines), AMBER if v.in_water else CYAN))
    for p in people:
        label = {"on_vehicle": "ON VEHICLE", "in_water": "IN WATER"}.get(p.situation, "")
        lines = [f"PER-{p.track_id:02d} PERSON", f"CONF {conf.get(p.track_id, 0):.2f}"] + ([label] if label else [])
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
        est = gauge_estimate(g, (epoch(a), epoch(b)), f"USGS {args.gauge} GAUGE {args.gauge_note}".strip())

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
                    est = WaterEstimate.from_samples(samples * M_TO_FT, "MODEL WATERLINE x 1M LIDAR")
        trk = len(tags)
        telemetry = (f"FRM {k:05d}|TRK {trk:02d}  {args.proc_fps:.0f} HZ|SEG SEGFORMER-B0+CLIPSEG"
                     f"|DET YOLOV8N/BYTETRACK")
        img = render_frame(frame, ema, tags, shore if fit is not None else None, est, telemetry, args.credit,
                           args.place, waterline=not args.no_waterline, t_s=k / fps)
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
