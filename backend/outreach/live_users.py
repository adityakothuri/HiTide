"""Per-user live outreach for the demo phone (e.g. HITIDE_LIVE_USERS=hc-dana).

Users listed here get real texts and calls even while PHOTON_MODE is mock (DATA_MODE=test), so one phone can
take a real call during the offline replay while the other ~250 simulated users stay mock. Every other guard
still applies: no sends to a moving driver, and the number must resolve through the allowlist
(env:DEMO_PHONE_* only; "sim:" phones are suppressed).
"""

from __future__ import annotations

import os

from outreach.mode import PhotonMode, parse_mode

DEFAULT_LIVE_PROVIDER: PhotonMode = "photon2"


def live_users() -> frozenset[str]:
    """User ids from HITIDE_LIVE_USERS (comma-separated)."""
    raw = os.environ.get("HITIDE_LIVE_USERS", "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def live_provider() -> PhotonMode:
    """HITIDE_LIVE_PROVIDER: photon2 (default) or stable. Never mock: a listed user is live by definition."""
    mode = parse_mode(os.environ.get("HITIDE_LIVE_PROVIDER"))
    return DEFAULT_LIVE_PROVIDER if mode == "mock" else mode
