"""Ryze Tello hookup for the indoor demo (overview.md 9.2-9.4). DRONE_MODE=tello; everything else stays simulated.

The planner's first real leg (bearing, distance) is scaled to a short indoor flight toward the mock crossing:
take off, turn to the bearing, fly forward <= 3 m at ~1 m height, hover 15 s while reading frames, land.
"Water" is a blue sheet or tray (pretrained flood models won't see a sheet as water), measured with an
OpenCV HSV threshold, the overview's demo fallback. Any error or lost video lands the drone and marks the
task failed, so the previous status stands (overview 22, failure drills).

Safety: ask the organizers first, prop guards on, clear area, low altitude. Connect the Tello through a USB
Wi-Fi adapter so the laptop's main Wi-Fi stays up for Photon and the backend.
Install: `uv pip install djitellopy` (optional, not a core dependency).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

MIN_MOVE_CM = 20          # Tello SDK minimum
MAX_MOVE_CM = 300         # indoor cap (SDK allows 500)
REAL_M_PER_INDOOR_CM = 20.0  # 5 km real -> 250 cm indoors
HOVER_S = 15.0
FRAME_EVERY_S = 0.5
WET_COVER_PCT = 15        # >= this share of the frame is "water on the road"
BLUE_LO = np.array([95, 80, 50], dtype=np.uint8)    # HSV (OpenCV hue 0-179)
BLUE_HI = np.array([130, 255, 255], dtype=np.uint8)


def indoor_moves(bearing_deg: float, distance_m: float) -> list[tuple[str, int]]:
    """Real leg -> Tello commands. Heading 0 = the direction the drone faces at take-off (= north on the map)."""
    turn = int(round(((bearing_deg + 180.0) % 360.0) - 180.0))  # shortest signed turn, clockwise positive
    forward = int(min(MAX_MOVE_CM, max(MIN_MOVE_CM, round(distance_m / REAL_M_PER_INDOOR_CM))))
    moves: list[tuple[str, int]] = []
    if turn:
        moves.append(("rotate", turn))
    moves.append(("forward", forward))
    return moves


def blue_sheet_cover_pct(frame_bgr: np.ndarray) -> int:
    import cv2

    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_LO, BLUE_HI)
    return int(round(100.0 * float(np.count_nonzero(mask)) / mask.size))


@dataclass(frozen=True)
class TelloResult:
    ok: bool
    road_covered_pct: int
    water_on_road: bool
    frames: int
    error: str | None = None


def fly_first_leg(bearing_deg: float, distance_m: float, tello: Any | None = None) -> TelloResult:
    """Blocking: run it in a worker thread. `tello` is injectable for tests; defaults to djitellopy.Tello()."""
    if tello is None:
        from djitellopy import Tello  # optional dependency
        tello = Tello()
    covers: list[int] = []
    flying = False
    try:
        tello.connect()
        tello.streamon()
        reader = tello.get_frame_read()
        flying = True  # before takeoff: if takeoff raises after the drone lifts, we still land
        tello.takeoff()
        for cmd, value in indoor_moves(bearing_deg, distance_m):
            if cmd == "rotate":
                (tello.rotate_clockwise if value > 0 else tello.rotate_counter_clockwise)(abs(value))
            else:
                tello.move_forward(value)
        end = time.monotonic() + HOVER_S
        while time.monotonic() < end:
            frame = reader.frame
            if frame is None:
                raise RuntimeError("video lost")
            covers.append(blue_sheet_cover_pct(frame[:, :, ::-1]))  # djitellopy frames are RGB
            time.sleep(FRAME_EVERY_S)
        cover = int(np.median(covers)) if covers else 0  # smoothed over the hover (overview 9.4)
        return TelloResult(True, cover, cover >= WET_COVER_PCT, len(covers))
    except Exception as exc:  # land on anything; the task fails and the old status stands
        log.exception("tello flight failed")
        return TelloResult(False, 0, False, len(covers), str(exc))
    finally:
        if flying:
            try:
                tello.land()
            except Exception:
                log.exception("tello land failed; use the emergency stop")
        try:
            tello.streamoff()
        except Exception:
            pass
