"""Append-only JSONL outreach log. Never receives phone numbers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = DATA_DIR / "outreach_log.jsonl"


_sink: Callable[[dict], None] | None = None


def set_sink(sink: Callable[[dict], None] | None) -> None:
    """Route the audit log to the database (SpacetimeDB outreach_event) instead of the JSONL file.
    The sink must not block (it enqueues a write-behind job). None restores the file."""
    global _sink
    _sink = sink


def append_log_file(payload: dict, path: Path = DEFAULT_LOG_PATH) -> bool:
    """The JSONL file, always (database-outage fallback)."""
    return _write_line(payload, path)


def append_log(payload: dict, path: Path = DEFAULT_LOG_PATH) -> bool:
    """Append one event to the database sink, else one JSON line. Returns False (and logs) on failure."""
    if _sink is not None and path == DEFAULT_LOG_PATH:   # an explicit path (tests) always means the file
        try:
            _sink(dict(payload))
            return True
        except Exception as exc:
            logger.error("outreach log sink failed: %s", type(exc).__name__)
            return _write_line(payload, path)
    return _write_line(payload, path)


def _write_line(payload: dict, path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("outreach log write failed: %s", type(exc).__name__)
        return False
    return True
