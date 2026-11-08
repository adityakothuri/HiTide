"""Enroll demo phones on the Photon 2.0 shared iMessage line and find the agent user id.

Run: uv run python -m scripts.photon2_enroll [--write-env]

For each DEMO_PHONE_A/B/C: create a shared-line assignment, then createOrGetUser.
The shared line's agent user is resolved by createOrGetUser on the assignedPhoneNumber
(shared Agents come back with details.type == "shared"). Never prints the API key or
full phone numbers.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_URL = "https://api.photon.codes"
TIMEOUT_S = 15.0
PLATFORM = "imessage"
DEMO_VARS = ("DEMO_PHONE_A", "DEMO_PHONE_B", "DEMO_PHONE_C")
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ENV_VAR = "PHOTON2_AGENT_USER_ID"


def mask(handle: str) -> str:
    if len(handle) <= 6:
        return "*" * len(handle)
    return handle[:2] + "*" * (len(handle) - 6) + handle[-4:]


def upsert_env(path: Path, key: str, value: str) -> None:
    """Set key=value in a dotenv file (atomic replace, mode 0600)."""
    lines = path.read_text().splitlines() if path.exists() else []
    entry = f"{key}={value}"
    replaced = False
    out: list[str] = []
    for line in lines:
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            if not replaced:
                out.append(entry)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(entry)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(out) + "\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def pick_agent_user_id(user: dict[str, Any]) -> str | None:
    """Return the user id when the record is a line Agent (details.type set), else None."""
    user_id = user.get("id")
    details = user.get("details")
    if not isinstance(user_id, str) or not isinstance(details, dict):
        return None
    if details.get("type") in ("shared", "dedicated"):
        return user_id
    return None


def _post(client: httpx.Client, url: str, body: dict[str, Any], key: str) -> dict[str, Any]:
    resp = client.post(url, json=body, headers={"Idempotency-Key": key})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("non-object response")
    return data


def run(write_env: bool) -> int:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("PHOTON2_API_KEY", "").strip()
    project = os.environ.get("PHOTON2_PROJECT_ID", "").strip()
    if not (api_key and project):
        logger.error("PHOTON2_API_KEY and PHOTON2_PROJECT_ID must be set in .env")
        return 1
    handles = [os.environ.get(v, "").strip() for v in DEMO_VARS]
    handles = [h for h in handles if h]
    if not handles:
        logger.error("no DEMO_PHONE_A/B/C set")
        return 1
    root = f"{BASE_URL}/v1/projects/{project}"
    agent_id: str | None = None
    agent_by_handle: dict[str, str] = {}  # shared line: each recipient gets its own line, so its own agent
    with httpx.Client(timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {api_key}"}) as client:
        for handle in handles:
            try:
                assign = _post(
                    client, f"{root}/platforms/imessage/assignments", {"handle": handle},
                    f"enroll-{uuid.uuid5(uuid.NAMESPACE_URL, project + handle)}",
                )
                _post(client, f"{root}/users", {"handle": handle, "platform": PLATFORM}, f"usr-{uuid.uuid4()}")
                line = str(assign.get("assignedPhoneNumber", ""))
                print(f"{mask(handle)} -> {line}")
                if line:
                    agent = _post(client, f"{root}/users", {"handle": line, "platform": PLATFORM}, f"agent-{uuid.uuid4()}")
                    this_agent = pick_agent_user_id(agent)
                    if this_agent:
                        agent_by_handle[handle] = this_agent
                        agent_id = agent_id or this_agent
            except httpx.HTTPStatusError as exc:
                logger.error("%s: HTTP %s", mask(handle), exc.response.status_code)
            except (httpx.HTTPError, ValueError) as exc:
                logger.error("%s: %s", mask(handle), type(exc).__name__)
    if agent_id is None:
        logger.error("could not resolve the shared-line agent user id")
        return 1
    agent_map = ",".join(f"{h}={a}" for h, a in agent_by_handle.items())
    print(f"{AGENT_ENV_VAR}={agent_id}")
    print(f"PHOTON2_AGENT_MAP: {len(agent_by_handle)} recipient(s) mapped to their line's agent")
    if write_env:
        upsert_env(REPO_ROOT / ".env", AGENT_ENV_VAR, agent_id)
        upsert_env(REPO_ROOT / ".env", "PHOTON2_AGENT_MAP", agent_map)
        print(f"wrote {AGENT_ENV_VAR} and PHOTON2_AGENT_MAP to .env")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-env", action="store_true", help="upsert PHOTON2_AGENT_USER_ID into ../.env")
    return run(parser.parse_args(argv).write_env)


if __name__ == "__main__":
    sys.exit(main())
