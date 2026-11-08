"""Append-only JSONL outreach log. Never receives phone numbers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = DATA_DIR / "outreach_log.jsonl"


def append_log(payload: dict, path: Path = DEFAULT_LOG_PATH) -> bool:
    """Append one JSON line. Returns False (and logs) on I/O failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("outreach log write failed: %s", type(exc).__name__)
        return False
    return True
