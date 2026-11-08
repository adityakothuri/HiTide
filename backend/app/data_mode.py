"""One switch for test vs real data: DATA_MODE=test|real (default test).

Applied once, before .env is loaded, so the precedence is:
    shell env  >  DATA_MODE preset  >  .env  >  code defaults
A stale value in .env (say REGION_MODE=live) therefore can't leak into test mode, while
`REGION_MODE=live ./dev.sh test` still works for one-off overrides.

Outreach is a separate switch on purpose: real texts and calls only go out with LIVE_OUTREACH=1,
whatever PHOTON_MODE says in .env.

DATA_MODE=manual skips the preset entirely (the test suite uses this).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

DataMode = Literal["test", "real", "manual"]

PRESETS: dict[str, dict[str, str]] = {
    "test": {
        "FEEDS_OFFLINE": "1",  # NWS/USGS from data/feeds_cache only, no network
        "REGION_MODE": "replay",  # Hill Country: July 4, 2025 replay
        "EVIDENCE_POLL_SECONDS": "0",  # no background Texas feed polling
        "FLOODWATCH_DB_BACKEND": "spacetime",  # primary; falls back to SQLite (logged) if it isn't running
        "SAFETY_DEMO": "1",  # compressed outreach-ladder timers
    },
    "real": {
        "FEEDS_OFFLINE": "0",
        "REGION_MODE": "live",
        "EVIDENCE_POLL_SECONDS": "120",
        "FLOODWATCH_DB_BACKEND": "spacetime",
    },
}

_LIVE_PHOTON = ("photon2", "stable", "photon")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_mode(env: Mapping[str, str], dotenv: Mapping[str, str | None]) -> DataMode:
    raw = (env.get("DATA_MODE") or dotenv.get("DATA_MODE") or "test").strip().lower()
    if raw not in ("test", "real", "manual"):
        raise ValueError("DATA_MODE must be 'test', 'real' or 'manual'")
    return raw  # type: ignore[return-value]


def apply_data_mode(env: dict[str, str] | os._Environ, dotenv: Mapping[str, str | None]) -> DataMode:
    """Set preset defaults into `env` (normally os.environ) before load_dotenv runs."""
    mode = resolve_mode(env, dotenv)
    env["DATA_MODE"] = mode
    if mode == "manual":
        return mode
    for key, value in PRESETS[mode].items():
        env.setdefault(key, value)
    live_outreach = mode == "real" and _truthy(env.get("LIVE_OUTREACH") or dotenv.get("LIVE_OUTREACH"))
    if live_outreach:
        chosen = (env.get("PHOTON_MODE") or dotenv.get("PHOTON_MODE") or "").strip().lower()
        env["PHOTON_MODE"] = chosen if chosen in _LIVE_PHOTON else "photon2"
    else:
        env["PHOTON_MODE"] = "mock"  # forced: no accidental texts from a stale .env
    return mode


def current_modes(region_mode: str | None = None, db: str | None = None) -> dict[str, str]:
    """What the running backend is actually using, for /api/health and the UI badge."""
    from outreach.mode import photon_mode

    return {
        "data_mode": os.environ.get("DATA_MODE", "manual"),
        "outreach": photon_mode(),
        "feeds": "cache" if _truthy(os.environ.get("FEEDS_OFFLINE")) else "live",
        "region": region_mode or os.environ.get("REGION_MODE", "replay"),
        "db": db or os.environ.get("FLOODWATCH_DB_BACKEND", "spacetime").lower(),
    }
