"""Add simulated flood-risk profiles to the existing data/drivers.json without regenerating routes.

Run: uv run python -m scripts.gen_profiles
Design and field sources: docs/driver-profile.md. All State Farm fields are simulated.
"""

from __future__ import annotations

import json
import logging

from app.config import DATA_DIR
from sim.drivers import load_drivers, save_drivers
from sim.profiles import attach_profiles

log = logging.getLogger("gen_profiles")
SEGMENTS_PATH = DATA_DIR / "town" / "segments.geojson"


def load_segments() -> list[dict]:
    return [f["properties"] for f in json.loads(SEGMENTS_PATH.read_text())["features"]]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    drivers = attach_profiles(load_drivers(), load_segments())
    save_drivers(drivers)
    with_crossings = sum(bool(d.profile["derived"]["frequent_crossings"]) for d in drivers)
    log.info("profiled %d drivers (%d use a low-lying crossing)", len(drivers), with_crossings)


if __name__ == "__main__":
    main()
