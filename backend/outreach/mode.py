"""Outreach send mode, read from PHOTON_MODE."""

from __future__ import annotations

import os
from typing import Literal

PhotonMode = Literal["mock", "stable", "photon2"]


def parse_mode(raw: str | None) -> PhotonMode:
    """mock (default) | stable (Spectrum sidecar; "photon" is the legacy alias) | photon2."""
    value = (raw or "").strip().lower()
    if value in ("stable", "photon"):
        return "stable"
    if value == "photon2":
        return "photon2"
    return "mock"


def photon_mode() -> PhotonMode:
    return parse_mode(os.environ.get("PHOTON_MODE"))
