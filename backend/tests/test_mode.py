"""photon_mode() env parsing."""

from __future__ import annotations

import pytest

from outreach.mode import photon_mode


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "mock"),
        ("", "mock"),
        ("mock", "mock"),
        ("stable", "stable"),
        ("photon", "stable"),
        ("PHOTON", "stable"),
        (" Photon2 ", "photon2"),
        ("photon2", "photon2"),
        ("bogus", "mock"),
    ],
)
def test_photon_mode(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("PHOTON_MODE", raising=False)
    else:
        monkeypatch.setenv("PHOTON_MODE", raw)
    assert photon_mode() == expected
