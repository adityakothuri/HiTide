"""Print-at-100% sheet of the four ArUco tags for the HiTide gauge tray.

    python backend/scripts/gauge_tag_sheet.py [--tray data/gauge_tray_160] [--dpi 600] [--check]

Reads <tray>/manifest.json (fiducials: dictionary, tag_mm, pad_mm, tags with centre_mm) and writes
<tray>/tag_sheet.png with the DPI stored in the PNG pHYs chunk, so a viewer that honours it prints
at actual size. Each marker is exactly tag_mm wide including its black border, sits in a white quiet
zone that fills the pad, and has a dashed cut square at pad_mm. The arrow beside each tag is the
marker's "up" (top edge = ArUco corners 0-1) and must point to tray +Y (toward tags 2 and 3).
The tags are laid out as they sit on the tray seen from above, +Y up the page.

Needs numpy and OpenCV with aruco (the Tello venv). PIL is used for nicer text when present.
--check re-detects the markers in the written PNG and verifies their size in pixels.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAY = ROOT / "data" / "gauge_tray_160"
MM_PER_INCH = 25.4

PAGE_W_MM = 190.0            # fits Letter and A4 inside normal printer margins
PAGE_H_MM = 178.0
CELL_X_MM = (40.0, 118.0)    # pad centres on the page: left / right column
CELL_Y_MM = (52.0, 112.0)    # pad centres on the page: top row (+Y side) / bottom row
SCALE_BAR_MM = 50.0
SCALE_BAR_Y_MM = 160.0
SCALE_BAR_X_MM = 15.0
LINE_MM = 0.25
DASH_MM, GAP_MM = 1.6, 1.0
GREY = 150
FONT_FILES = ("C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT_FILES = ("C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
SIDE_NAMES = {(False, False): "low X, low Y", (True, False): "high X, low Y",
              (True, True): "high X, high Y", (False, True): "low X, high Y"}


class Sheet:
    """A white grayscale canvas addressed in millimetres."""

    def __init__(self, width_mm: float, height_mm: float, dpi: int) -> None:
        self.dpi = dpi
        self.px_per_mm = dpi / MM_PER_INCH
        self.img = np.full((self.px(height_mm), self.px(width_mm)), 255, np.uint8)

    def px(self, mm: float) -> int:
        return int(round(mm * self.px_per_mm))

    def pt(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        return self.px(x_mm), self.px(y_mm)

    def line(self, a: tuple[float, float], b: tuple[float, float], width_mm: float = LINE_MM,
             value: int = 0) -> None:
        cv2.line(self.img, self.pt(*a), self.pt(*b), int(value), max(1, self.px(width_mm)), cv2.LINE_AA)

    def dashed_square(self, cx: float, cy: float, side: float) -> None:
        h = side / 2
        corners = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
        for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
            length = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            d = 0.0
            while d < length:
                e = min(d + DASH_MM, length)
                p = (a[0] + (b[0] - a[0]) * d / length, a[1] + (b[1] - a[1]) * d / length)
                q = (a[0] + (b[0] - a[0]) * e / length, a[1] + (b[1] - a[1]) * e / length)
                self.line(p, q, value=GREY)
                d = e + GAP_MM

    def arrow_up(self, x: float, y_bottom: float, y_top: float, width_mm: float = 0.6) -> None:
        self.line((x, y_bottom), (x, y_top + 1.0), width_mm)
        head = np.array([self.pt(x, y_top), self.pt(x - 1.8, y_top + 3.2), self.pt(x + 1.8, y_top + 3.2)])
        cv2.fillPoly(self.img, [head], 0, cv2.LINE_AA)

    def marker(self, bits: np.ndarray, cx: float, cy: float, side_mm: float) -> None:
        """Paint the marker cells with exact pixel edges so the total width is round(side_mm in px)."""
        n = bits.shape[0]
        x0 = self.px(cx - side_mm / 2)
        y0 = self.px(cy - side_mm / 2)
        width = self.px(side_mm)
        edges = [int(round(i * width / n)) for i in range(n + 1)]
        for r in range(n):
            for c in range(n):
                self.img[y0 + edges[r]:y0 + edges[r + 1], x0 + edges[c]:x0 + edges[c + 1]] = bits[r, c]

    def text(self, s: str, x: float, y: float, cap_mm: float, bold: bool = False) -> None:
        """Draw s with its top-left at (x, y) mm, letters about cap_mm tall."""
        size_px = max(8, int(cap_mm * self.px_per_mm / 0.72))
        font = _load_font(BOLD_FONT_FILES if bold else FONT_FILES, size_px)
        if font is not None:
            from PIL import Image, ImageDraw

            canvas = Image.fromarray(self.img)
            ImageDraw.Draw(canvas).text(self.pt(x, y), s, fill=0, font=font)
            self.img = np.asarray(canvas).copy()
            return
        scale = cap_mm * self.px_per_mm / 22.0
        thick = max(1, int(round(scale * (2.2 if bold else 1.4))))
        ox, oy = self.pt(x, y + cap_mm)
        cv2.putText(self.img, s, (ox, oy), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, thick, cv2.LINE_AA)


def _load_font(candidates: tuple[str, ...], size_px: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for f in candidates:
        if Path(f).exists():
            return ImageFont.truetype(f, size_px)
    return None


def png_with_dpi(img: np.ndarray, dpi: int) -> bytes:
    """Encode img as PNG and insert a pHYs chunk (pixels per metre) right after IHDR."""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    data = buf.tobytes()
    ppm = int(round(dpi / 0.0254))
    body = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    ihdr_end = 8 + 4 + 4 + 13 + 4                 # signature + IHDR length, type, data, crc
    return data[:ihdr_end] + chunk + data[ihdr_end:]


def side_name(centre: list[float], size: float) -> str:
    return SIDE_NAMES[(centre[0] > size / 2, centre[1] > size / 2)]


def build_sheet(manifest: dict, dpi: int) -> np.ndarray:
    fid = manifest["fiducials"]
    tag_mm, pad_mm = float(fid["tag_mm"]), float(fid["pad_mm"])
    size_x, size_y = manifest["size_mm"][0], manifest["size_mm"][1]
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, fid["dictionary"]))
    sheet = Sheet(PAGE_W_MM, PAGE_H_MM, dpi)

    sheet.text(f"HiTide gauge tray tags ({size_x:.0f} mm tray)", 10, 7, 4.2, bold=True)
    sheet.text(f"{fid['dictionary']}, each tag {tag_mm:.1f} mm wide including the black border. "
               f"Cut on the dashed {pad_mm:.1f} mm square.", 10, 14, 2.4)
    sheet.text("Laid out as on the tray seen from above. Arrow = tray +Y (toward tags 2 and 3, "
               "the GUADALUPE RIVER rim).", 10, 18.5, 2.4)

    for tag in fid["tags"]:
        tid = int(tag["id"])
        cx_t, cy_t = tag["centre_mm"][0], tag["centre_mm"][1]
        cx = CELL_X_MM[1] if cx_t > size_x / 2 else CELL_X_MM[0]
        cy = CELL_Y_MM[0] if cy_t > size_y / 2 else CELL_Y_MM[1]
        bits = cv2.aruco.generateImageMarker(dictionary, tid, dictionary.markerSize + 2)
        sheet.marker(bits, cx, cy, tag_mm)
        sheet.dashed_square(cx, cy, pad_mm)
        ax = cx + pad_mm / 2 + 5.0
        sheet.arrow_up(ax, cy + pad_mm / 2, cy - pad_mm / 2)
        sheet.text("+Y", ax + 2.5, cy - pad_mm / 2, 2.6, bold=True)
        sheet.text("up", ax + 2.5, cy - pad_mm / 2 + 4.0, 2.2)
        ty = cy + pad_mm / 2 + 3.0
        sheet.text(f"ID {tid}", cx - pad_mm / 2, ty, 3.0, bold=True)
        sheet.text(f"pad centre x,y = {cx_t:.1f}, {cy_t:.1f} mm ({side_name(tag['centre_mm'], size_x)})",
                   cx - pad_mm / 2, ty + 4.6, 2.2)

    x0, y = SCALE_BAR_X_MM, SCALE_BAR_Y_MM
    sheet.line((x0, y), (x0 + SCALE_BAR_MM, y), 0.5)
    for k in range(int(SCALE_BAR_MM / 10) + 1):
        tick = 3.0 if k in (0, int(SCALE_BAR_MM / 10)) else 1.8
        sheet.line((x0 + 10 * k, y - tick), (x0 + 10 * k, y), 0.35)
    sheet.text(f"{SCALE_BAR_MM:.1f} mm", x0, y + 2.0, 2.4, bold=True)
    sheet.text("Print at 100% / actual size (no 'fit to page').", x0 + SCALE_BAR_MM + 6, y - 5.0, 2.6, bold=True)
    sheet.text(f"Measure this bar: it must be {SCALE_BAR_MM:.1f} mm (+/- 0.5). "
               f"Tag black square = {tag_mm:.1f} mm.", x0 + SCALE_BAR_MM + 6, y, 2.4)
    return sheet.img


def check_sheet(path: Path, manifest: dict, dpi: int) -> bool:
    """Re-detect the markers in the PNG; check ids, size in px and that corner 0 is top-left."""
    fid = manifest["fiducials"]
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, fid["dictionary"]))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX   # without it corners sit on pixel centres (-1 px)
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary, params).detectMarkers(img)
    expected = float(fid["tag_mm"]) / MM_PER_INCH * dpi
    found = sorted(int(i) for i in ids.ravel()) if ids is not None else []
    ok = found == sorted(int(t["id"]) for t in fid["tags"])
    print(f"  detected ids {found}, expected width {expected:.2f} px at {dpi} dpi")
    for c, i in zip(corners, ids.ravel() if ids is not None else [], strict=True):
        q = c.reshape(4, 2)
        sides = [float(np.linalg.norm(q[(k + 1) % 4] - q[k])) for k in range(4)]
        width = float(np.mean(sides))
        upright = int(np.argmin(q.sum(axis=1))) == 0            # corner 0 is top-left: marker up = page up
        good = abs(width - expected) <= 1.0 and upright
        ok = ok and good
        print(f"  ID {int(i)}: width {width:.2f} px (sides {', '.join(f'{s:.1f}' for s in sides)}), "
              f"up = page up {upright}, {'OK' if good else 'FAIL'}")
    with path.open("rb") as f:
        head = f.read(64)
    k = head.find(b"pHYs")
    ppm = struct.unpack(">I", head[k + 4:k + 8])[0] if k > 0 else 0
    dpi_ok = k > 0 and abs(ppm * 0.0254 - dpi) < 0.5
    print(f"  pHYs {ppm} px/m = {ppm * 0.0254:.1f} dpi, {'OK' if dpi_ok else 'FAIL'}")
    return ok and dpi_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Write the printable ArUco tag sheet for a gauge tray")
    ap.add_argument("--tray", type=Path, default=DEFAULT_TRAY, help="tray directory with manifest.json")
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--check", action="store_true", help="re-detect the markers in the written PNG")
    args = ap.parse_args()
    if args.dpi < 150:
        ap.error("--dpi must be at least 150 for a crisp 16 mm tag")
    manifest_path = args.tray / "manifest.json"
    if not manifest_path.exists():
        ap.error(f"no manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    img = build_sheet(manifest, args.dpi)
    out = args.tray / "tag_sheet.png"
    out.write_bytes(png_with_dpi(img, args.dpi))
    print(f"Wrote {out} ({img.shape[1]} x {img.shape[0]} px, {PAGE_W_MM:.0f} x {PAGE_H_MM:.0f} mm at {args.dpi} dpi)")
    if args.check and not check_sheet(out, manifest, args.dpi):
        print("  CHECK FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
