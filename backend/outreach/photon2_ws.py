"""Receive iMessage replies and poll votes from Photon 2.0 over its Socket.IO event stream.

Docs (beta): https://photon.codes/docs/beta/websocket/connect  (+ /session, /events, /cursors, /errors)
Server: https://api.photon.codes, Socket.IO path /v1/projects/{projectId}/events/ws, default namespace,
websocket transport only, header "Authorization: Bearer <pho_sk_...>". On every connect emit
`subscribe {"startSeq": N}` with an ack; deliveries then arrive as `delivery(event, {"seq", "replyExpected"})`.
Deliveries have no ack. No public URL or tunnel is needed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import socketio

from outreach.inbound import mask_phone
from outreach.replies import parse_reply

log = logging.getLogger("outreach.photon2_ws")

DEFAULT_ORIGIN = "https://api.photon.codes"
SUBSCRIBE_TIMEOUT_S = 10
RECONNECT_MIN_S = 1
RECONNECT_MAX_S = 30
QUEUE_MAX = 128

OnMessage = Callable[[str, str], Awaitable[None]]


def _poll_vote_text(content: dict[str, Any]) -> str | None:
    """Option id (safe / need_help -> help); an opaque id falls back to the option text."""
    options = content.get("selectedOptions")
    if not isinstance(options, list):
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        oid, otext = str(opt.get("id") or ""), str(opt.get("text") or "")
        if oid == "need_help":
            return "help"
        for candidate in (oid, otext):
            if candidate and parse_reply(candidate) is not None:
                return candidate
    return None


def parse_ws_event(event: dict[str, Any]) -> tuple[str, str] | None:
    """(sender_handle, text) for an inbound text or poll vote; None for our own sends or anything else."""
    if not isinstance(event, dict) or event.get("type") != "message.received":
        return None
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict) or obj.get("status") != "received":
        return None
    sent_by, content = obj.get("sentBy"), obj.get("content")
    handle = sent_by.get("handle") if isinstance(sent_by, dict) else None
    if not isinstance(handle, str) or not handle.strip() or not isinstance(content, dict):
        return None
    kind = content.get("type")
    text = content.get("text") if kind == "text" else _poll_vote_text(content) if kind == "poll.vote" else None
    if not isinstance(text, str) or not text:
        return None
    return handle.strip(), text


class Photon2Inbound:
    """Socket.IO client with reconnect and backoff. Inert unless PHOTON_MODE=photon2 and a key is set."""

    def __init__(self) -> None:
        self._sio: socketio.AsyncClient | None = None
        self._worker: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[tuple[dict[str, Any], int]] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._on_message: OnMessage | None = None
        self._cursor = 0  # in-memory only; replay after reconnect within one process run

    @property
    def running(self) -> bool:
        return self._sio is not None

    async def start(self, on_message: OnMessage) -> None:
        if os.environ.get("PHOTON_MODE") != "photon2":
            return
        key = os.environ.get("PHOTON2_API_KEY", "").strip()
        project = os.environ.get("PHOTON2_PROJECT_ID", "").strip()
        if not key or not project:
            log.warning("photon2 inbound disabled: PHOTON2_API_KEY or PHOTON2_PROJECT_ID missing")
            return
        self._on_message = on_message
        self._sio = self._build_client()
        self._worker = asyncio.create_task(self._work(), name="photon2-inbound-worker")
        self._connector = asyncio.create_task(self._connect(key, project), name="photon2-inbound-connect")

    async def stop(self) -> None:
        sio, worker, connector = self._sio, self._worker, getattr(self, "_connector", None)
        self._sio = self._worker = self._connector = None
        tasks = [t for t in (connector, worker) if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)  # nothing left half-connected after shutdown
        if sio:
            try:
                await sio.disconnect()
            except Exception as exc:  # shutdown must never raise
                log.warning("photon2 inbound disconnect failed: %s", type(exc).__name__)
        log.info("photon2 inbound stopped")

    def _build_client(self) -> socketio.AsyncClient:
        sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_delay=RECONNECT_MIN_S,
            reconnection_delay_max=RECONNECT_MAX_S,
            randomization_factor=0.5,
            logger=False,
            engineio_logger=False,
        )

        @sio.event
        async def connect() -> None:
            try:  # subscribe again on every (re)connect, resuming from the last cursor handled
                result = await sio.call("subscribe", {"startSeq": self._cursor}, timeout=SUBSCRIBE_TIMEOUT_S)
            except Exception as exc:
                log.error("photon2 subscribe failed: %s", type(exc).__name__)
                return  # the server closes an unsubscribed connection, and the client then reconnects
            ok = isinstance(result, dict) and result.get("ok") is True
            if not ok:
                code = (result or {}).get("error", {}).get("code") if isinstance(result, dict) else None
                log.error("photon2 subscribe rejected: %s", code)
                return
            log.info("photon2 inbound connected and subscribed (startSeq=%d)", self._cursor)

        @sio.event
        async def disconnect() -> None:
            log.warning("photon2 inbound disconnected; client will retry with backoff")

        @sio.event
        async def connect_error(data: Any) -> None:
            log.error("photon2 connect error: %s", data if isinstance(data, str) else type(data).__name__)

        @sio.on("delivery_error")
        async def delivery_error(error: Any) -> None:
            code = error.get("code") if isinstance(error, dict) else None
            log.error("photon2 delivery_error: %s", code)

        @sio.on("delivery")
        async def delivery(event: Any, metadata: Any = None) -> None:
            seq = metadata.get("seq") if isinstance(metadata, dict) else None
            try:
                self._queue.put_nowait((event, seq if isinstance(seq, int) else self._cursor))
            except asyncio.QueueFull:
                log.error("photon2 delivery queue full; dropping seq=%s", seq)

        return sio

    async def _connect(self, key: str, project: str) -> None:
        """Initial connect; python-socketio's own reconnect only starts after a first success."""
        delay = RECONNECT_MIN_S
        origin = os.environ.get("PHOTON_API_ORIGIN", DEFAULT_ORIGIN)
        while (sio := self._sio) is not None:
            try:
                await sio.connect(
                    origin,
                    socketio_path=f"/v1/projects/{project}/events/ws",
                    transports=["websocket"],
                    headers={"Authorization": f"Bearer {key}"},
                    wait_timeout=SUBSCRIBE_TIMEOUT_S,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("photon2 initial connect failed (%s); retry in %ds", type(exc).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_S)

    async def _work(self) -> None:
        """Handle deliveries one at a time, in order; a bad handler never kills the worker."""
        while True:
            event, seq = await self._queue.get()
            parsed = parse_ws_event(event)
            if parsed is not None and self._on_message is not None:
                sender, text = parsed
                try:
                    await self._on_message(sender, text)
                except Exception as exc:
                    log.error("photon2 inbound handler failed for %s: %s", mask_phone(sender), type(exc).__name__)
            self._cursor = max(self._cursor, seq)
