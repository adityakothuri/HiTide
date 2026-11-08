"""Load backend/config/vision.yaml (plus the road depth bands from weights.yaml) once, read-only."""

from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from app.config import BACKEND_DIR, settings

VISION_CONFIG_PATH = BACKEND_DIR / "config" / "vision.yaml"
REQUIRED_SECTIONS = (
    "models", "classes", "segmentation", "grid", "edges", "water_level",
    "road", "detect", "objects", "vehicle_band_in", "rise", "alerts",
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@lru_cache(maxsize=1)
def vision_config() -> Mapping[str, Any]:
    """Validated, immutable vision config. Road bands come from weights.yaml (single source of truth)."""
    with VISION_CONFIG_PATH.open() as fh:
        raw = yaml.safe_load(fh)
    missing = [s for s in REQUIRED_SECTIONS if s not in raw]
    if missing:
        raise ValueError(f"vision.yaml missing sections: {missing}")
    raw["road_band_in"] = dict(settings()["road_status_in"])
    return _freeze(raw)
