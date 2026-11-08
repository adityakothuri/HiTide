"""WebSocket hub: fan out WsEvent envelopes to every connected client."""

from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any

from fastapi import WebSocket

from sim.engine import now_iso

log = logging.getLogger(__name__)


class WsHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._seq = itertools.count(1)
        self._lock = asyncio.Lock()

    def envelope(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"type": type_, "seq": next(self._seq), "ts": now_iso(), "payload": payload}

    async def connect(self, ws: WebSocket, snapshot: dict[str, Any]) -> None:
        await ws.accept()
        await ws.send_json(self.envelope("snapshot", snapshot))
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        msg = self.envelope(type_, payload)
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001 - client went away
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)
