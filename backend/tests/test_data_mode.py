"""DATA_MODE preset: shell beats preset beats .env; outreach only goes live on explicit opt-in."""

import pytest

from app.data_mode import apply_data_mode


def test_default_is_test_mode_offline_and_mock():
    env: dict[str, str] = {}
    assert apply_data_mode(env, {}) == "test"
    assert env["FEEDS_OFFLINE"] == "1"
    assert env["REGION_MODE"] == "replay"
    assert env["HITIDE_DB_BACKEND"] == "spacetime"  # primary; the factory falls back to SQLite if it is down
    assert env["EVIDENCE_POLL_SECONDS"] == "0"
    assert env["PHOTON_MODE"] == "mock"


def test_preset_beats_stale_dotenv_values():
    env: dict[str, str] = {}
    apply_data_mode(env, {"REGION_MODE": "live", "HITIDE_DB_BACKEND": "mongodb", "PHOTON_MODE": "photon2"})
    assert env["REGION_MODE"] == "replay"
    assert env["HITIDE_DB_BACKEND"] == "spacetime"  # primary; the factory falls back to SQLite if it is down
    assert env["PHOTON_MODE"] == "mock"


def test_shell_env_beats_preset():
    env = {"REGION_MODE": "live"}
    apply_data_mode(env, {})
    assert env["REGION_MODE"] == "live"


def test_data_mode_can_come_from_dotenv():
    env: dict[str, str] = {}
    assert apply_data_mode(env, {"DATA_MODE": "real"}) == "real"
    assert env["FEEDS_OFFLINE"] == "0"
    assert env["REGION_MODE"] == "live"


def test_real_mode_keeps_outreach_mock_without_opt_in():
    env = {"DATA_MODE": "real"}
    apply_data_mode(env, {"PHOTON_MODE": "photon2"})
    assert env["PHOTON_MODE"] == "mock"


def test_real_mode_live_outreach_uses_dotenv_photon_or_photon2():
    env = {"DATA_MODE": "real", "LIVE_OUTREACH": "1"}
    apply_data_mode(env, {"PHOTON_MODE": "stable"})
    assert env["PHOTON_MODE"] == "stable"
    env2 = {"DATA_MODE": "real", "LIVE_OUTREACH": "1"}
    apply_data_mode(env2, {})
    assert env2["PHOTON_MODE"] == "photon2"


def test_live_outreach_is_ignored_in_test_mode():
    env = {"LIVE_OUTREACH": "1", "PHOTON_MODE": "photon2"}
    apply_data_mode(env, {})
    assert env["PHOTON_MODE"] == "mock"


def test_manual_mode_touches_nothing():
    env = {"DATA_MODE": "manual", "PHOTON_MODE": "photon2"}
    apply_data_mode(env, {})
    assert env == {"DATA_MODE": "manual", "PHOTON_MODE": "photon2"}


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        apply_data_mode({"DATA_MODE": "prod"}, {})
