"""Feed a real VisionSnapshot into the Hill Country critical-point loop (overview 6.3 drone override).

Kept outside critical/loop.py on purpose: the loop only reads `water_on_road` and `t` from an observation
(DroneObs(wet, age)), plus asdict() for the API, so a field-compatible frozen dataclass is enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vision.snapshot import VisionSnapshot


@dataclass(frozen=True)
class LoopObs:
    """Field-compatible with critical.loop.Snapshot (same types: the loop compares est_depth_in >= 24).

    Unknown depth is stored as 0.0 with depth_method "none", the loop's own convention for a depth-less
    observation (CriticalLoop.external_snapshot). The honest null is what goes out over the API and WS.
    `t` is the replay time at receipt: the loop ages observations on its own clock.
    """
    point_id: str
    drone_id: str
    time: str
    t: float
    water_on_road: bool
    road_covered_pct: int | None      # display only in the loop; unknown stays None
    est_depth_in: float
    depth_method: str
    rising: bool | None
    people_seen: int
    confidence: str
    image_url: str | None
    simulated: bool


def apply_to_loop(loop: Any, snap: VisionSnapshot) -> tuple[bool, str]:
    """Record the snapshot as the point's drone observation. Returns (fused, why-not)."""
    if snap.water_on_road is None:
        return False, "water_on_road unknown: not used by fusion (never treated as dry)"
    with loop.lock:
        if snap.point_id not in loop.points:
            return False, "not a Hill Country critical point"
        if loop.t is None:
            return False, "scenario not running"
        loop.obs[snap.point_id] = LoopObs(
            snap.point_id, snap.drone_id or "drone-vision", snap.time.isoformat(), float(loop.t), snap.water_on_road,
            None if snap.road_covered_pct is None else int(round(snap.road_covered_pct)), snap.est_depth_in if snap.est_depth_in is not None else 0.0,
            snap.depth_method, snap.rising, snap.people_seen,
            snap.confidence, snap.image_url, snap.simulated,
        )
        loop.points_checked.add(snap.point_id)
        loop.force_replan = True
    return True, ""
