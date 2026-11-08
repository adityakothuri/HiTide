"""WebSocket hub: fan out WsEvent envelopes to every connected client."""

from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any, Callable

from fastapi import WebSocket

from sim.engine import now_iso

log = logging.getLogger(__name__)
SEND_TIMEOUT_S = 2.0


class WsHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._seq = itertools.count(1)
        self._lock = asyncio.Lock()

    def envelope(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"type": type_, "seq": next(self._seq), "ts": now_iso(), "payload": payload}

    async def connect(self, ws: WebSocket, snapshot: Callable[[], dict[str, Any]]) -> None:
        await ws.accept()
        async with self._lock:  # emit() also takes the lock, so no event slips between snapshot and join
            await ws.send_json(self.envelope("snapshot", snapshot()))
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        msg = self.envelope(type_, payload)
        async with self._lock:
            clients = list(self._clients)
        results = await asyncio.gather(
            *(asyncio.wait_for(ws.send_json(msg), SEND_TIMEOUT_S) for ws in clients), return_exceptions=True
        )
        for ws, res in zip(clients, results):
            if isinstance(res, BaseException):
                await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)
