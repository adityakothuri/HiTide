"""Photon 2.0 adapter (https://api.photon.codes).

Flow per send: createOrGetUser(handle) -> createOrGetSpace([agent, user]) ->
sendMessage(spaceId, senderId=agent). User and space ids are cached per process.
Functions return "sent" or "failed" and never raise. Phone numbers are masked in
logs and the API key is never logged.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.photon.codes"
TIMEOUT_S = 8.0
PLATFORM = "imessage"
POLL_OPTION_IDS = ("safe", "need_help")

Status = Literal["sent", "failed"]

_USER_CACHE: dict[str, str] = {}
_SPACE_CACHE: dict[str, str] = {}


class _Photon2Error(Exception):
    """Internal: any failed step. Never escapes this module."""


@dataclass(frozen=True)
class _Config:
    api_key: str
    project_id: str
    agent_user_id: str


def reset_cache() -> None:
    _USER_CACHE.clear()
    _SPACE_CACHE.clear()


def mask_handle(handle: str) -> str:
    if len(handle) <= 6:
        return "*" * len(handle)
    return handle[:2] + "*" * (len(handle) - 6) + handle[-4:]


def agent_map() -> dict[str, str]:
    """PHOTON2_AGENT_MAP="+1555...=pho_usr_...,+1555...=pho_usr_..." (written by scripts.photon2_enroll).

    On a shared line every recipient gets its own assigned line, so each has its own agent sender.
    """
    out: dict[str, str] = {}
    for pair in os.environ.get("PHOTON2_AGENT_MAP", "").split(","):
        handle, _, agent = (part.strip() for part in pair.partition("="))
        if handle and agent:
            out[handle] = agent
    return out


def _agent_for(handle: str, cfg: _Config) -> str:
    return agent_map().get(handle, cfg.agent_user_id)


def configured() -> bool:
    return _load_config() is not None


def _load_config() -> _Config | None:
    key = os.environ.get("PHOTON2_API_KEY", "").strip()
    project = os.environ.get("PHOTON2_PROJECT_ID", "").strip()
    agent = os.environ.get("PHOTON2_AGENT_USER_ID", "").strip()
    if not (key and project and agent):
        return None
    return _Config(key, project, agent)


async def _post(
    client: httpx.AsyncClient, cfg: _Config, path: str, body: Mapping[str, Any], idem_key: str
) -> dict[str, Any]:
    resp = await client.post(
        f"{BASE_URL}/v1/projects/{cfg.project_id}{path}",
        json=body,
        headers={"Authorization": f"Bearer {cfg.api_key}", "Idempotency-Key": idem_key},
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise _Photon2Error(f"{path} returned non-object")
    return data


def _require_id(data: Mapping[str, Any], path: str) -> str:
    value = data.get("id")
    if not isinstance(value, str) or not value:
        raise _Photon2Error(f"{path} response missing id")
    return value


async def _ensure_space(client: httpx.AsyncClient, cfg: _Config, handle: str) -> str:
    user_id = _USER_CACHE.get(handle)
    if user_id is None:
        data = await _post(
            client, cfg, "/users", {"handle": handle, "platform": PLATFORM}, f"usr-{uuid.uuid4().hex}"
        )
        user_id = _require_id(data, "/users")
        _USER_CACHE[handle] = user_id
    agent = _agent_for(handle, cfg)
    cache_key = f"{agent}:{user_id}"
    space_id = _SPACE_CACHE.get(cache_key)
    if space_id is None:
        data = await _post(
            client,
            cfg,
            "/spaces",
            {"participantIds": [agent, user_id], "platform": PLATFORM},
            f"spc-{user_id}",
        )
        space_id = _require_id(data, "/spaces")
        _SPACE_CACHE[cache_key] = space_id
    return space_id


async def _send(
    handle: str, content: Mapping[str, Any], transport: httpx.AsyncBaseTransport | None
) -> Status:
    cfg = _load_config()
    if cfg is None:
        logger.error("photon2 env missing (PHOTON2_API_KEY/PROJECT_ID/AGENT_USER_ID)")
        return "failed"
    masked = mask_handle(handle)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            space_id = await _ensure_space(client, cfg, handle)
            await _post(
                client,
                cfg,
                "/messages",
                {"spaceId": space_id, "senderId": _agent_for(handle, cfg), "content": dict(content)},
                f"msg-{uuid.uuid4()}",
            )
    except httpx.HTTPStatusError as exc:
        logger.error("photon2 HTTP %s for %s", exc.response.status_code, masked)
        return "failed"
    except (httpx.HTTPError, _Photon2Error, ValueError) as exc:
        logger.error("photon2 error for %s: %s", masked, type(exc).__name__)
        return "failed"
    return "sent"


async def send_text(
    handle: str, text: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> Status:
    return await _send(handle, {"type": "text", "format": "plain", "text": text}, transport)


async def send_poll(
    handle: str,
    question: str,
    options: Sequence[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Status:
    # Option ids are stable ("safe"/"need_help") so inbound votes map to reply parsing.
    ids = list(POLL_OPTION_IDS)
    poll_options = [
        {"id": ids[i] if i < len(ids) else f"option_{i + 1}", "text": text}
        for i, text in enumerate(options)
    ]
    content = {"type": "poll", "question": question, "selectionMode": "single", "options": poll_options}
    return await _send(handle, content, transport)
