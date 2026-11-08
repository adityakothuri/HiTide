"""Lookup of precomputed drone vision results (filled in Phase 5 by scripts/run_vision_batch.py)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import DATA_DIR

log = logging.getLogger(__name__)
RESULTS_PATH = DATA_DIR / "drone_samples" / "results.json"


def result_for(night: bool, recommendation: str) -> tuple[dict[str, Any] | None, int | None]:
    """(VisionResult dict, people_count) for the demo case, or (None, None) if vision isn't built yet."""
    try:
        results = json.loads(RESULTS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        log.warning("no vision results at %s", RESULTS_PATH)
        return None, None
    pick = results.get("demo_case") or next(iter(results.get("images", {}).values()), None)
    if not pick:
        return None, None
    vision = {**pick, "night_mode": night, "thermal_simulated": night, "recommendation": recommendation}
    return vision, len(vision.get("people", []))
