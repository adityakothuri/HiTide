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
