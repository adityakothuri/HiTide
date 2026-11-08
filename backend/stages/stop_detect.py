"""Stage 3 trigger: is a car stopped in floodwater? Pure function, thresholds come from weights.yaml."""

from __future__ import annotations

STOPPED_SPEED_MPS = 0.5


def is_stopped_in_water(
    speed_mps: float,
    stationary_for_s: float,
    dist_to_nearest_dest_m: float,
    depth_in: float,
    stop_seconds: float,
    dest_radius_m: float,
    caution_in: float = 3.0,
) -> bool:
    """True only when slow, stationary long enough, away from any destination, and in water."""
    return (
        speed_mps < STOPPED_SPEED_MPS
        and stationary_for_s >= stop_seconds
        and dist_to_nearest_dest_m > dest_radius_m
        and depth_in >= caution_in
    )
