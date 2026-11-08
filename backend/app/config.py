"""Load tunables from config/weights.yaml once."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = REPO_DIR / "data"
CONFIG_PATH = BACKEND_DIR / "config" / "weights.yaml"


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def fusion_settings() -> dict[str, Any]:
    """config/fusion.yaml: evidence fusion and critical-point priority weights (overview.md 6.3, 8.4)."""
    with (BACKEND_DIR / "config" / "fusion.yaml").open() as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=4)
def region_settings(region_id: str = "hill_country") -> dict[str, Any]:
    with (BACKEND_DIR / "config" / "regions" / f"{region_id}.yaml").open() as fh:
        return yaml.safe_load(fh)
