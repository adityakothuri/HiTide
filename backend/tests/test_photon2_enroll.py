"""Pure helpers of scripts.photon2_enroll: masking, env upsert, agent id pick."""

from __future__ import annotations

import os
import stat

from scripts.photon2_enroll import mask, pick_agent_user_id, upsert_env

AGENT = "pho_usr_" + "a" * 25


def test_mask():
    assert mask("+18305550123") == "+1******0123"
    assert mask("") == ""
    assert mask("abc") == "***"


def test_upsert_env_creates_file_with_0600(tmp_path):
    p = tmp_path / ".env"
    upsert_env(p, "PHOTON2_AGENT_USER_ID", AGENT)
    assert p.read_text() == f"PHOTON2_AGENT_USER_ID={AGENT}\n"
    # Windows chmod does not implement POSIX owner/group permission bits.
    # Content/atomic-write behavior is portable; ACL privacy needs separate validation.
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_upsert_env_replaces_existing_and_keeps_others(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\nPHOTON2_AGENT_USER_ID=old\n# c\nB=2")
    p.chmod(0o644)
    upsert_env(p, "PHOTON2_AGENT_USER_ID", AGENT)
    assert p.read_text() == f"A=1\nPHOTON2_AGENT_USER_ID={AGENT}\n# c\nB=2\n"
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_upsert_env_appends_when_missing(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\n")
    upsert_env(p, "X", "y")
    assert p.read_text() == "A=1\nX=y\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_pick_agent_from_user_object():
    user = {"id": AGENT, "details": {"type": "shared"}}
    assert pick_agent_user_id(user) == AGENT


def test_pick_agent_rejects_human_or_malformed():
    assert pick_agent_user_id({"id": AGENT, "details": {}}) is None
    assert pick_agent_user_id({"id": AGENT, "details": {"type": "dedicated"}}) == AGENT
    assert pick_agent_user_id({"details": {"type": "shared"}}) is None
    assert pick_agent_user_id({}) is None
