"""Outreach send mode, read from PHOTON_MODE."""

from __future__ import annotations

import os
from typing import Literal

PhotonMode = Literal["mock", "stable", "photon2"]


def photon_mode() -> PhotonMode:
    """mock (default) | stable (Spectrum sidecar; "photon" is the legacy alias) | photon2."""
    raw = os.environ.get("PHOTON_MODE", "").strip().lower()
    if raw in ("stable", "photon"):
        return "stable"
    if raw == "photon2":
        return "photon2"
    return "mock"
