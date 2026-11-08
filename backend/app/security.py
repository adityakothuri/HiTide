"""Same-origin guard for state-changing routes and the WebSocket.

CORS doesn't cover WebSockets or no-body POSTs, so a random page in the demo browser could otherwise read live
locations or reset the demo. Requests with no Origin (curl, the Photon sidecar) are allowed.
"""

from __future__ import annotations

import os
import re

from fastapi import HTTPException, Request

DEFAULT_ORIGINS = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
ORIGIN_RE = re.compile(os.environ.get("FRONTEND_ORIGIN_REGEX", DEFAULT_ORIGINS))


def origin_ok(origin: str | None) -> bool:
    return origin is None or ORIGIN_RE.fullmatch(origin) is not None


async def require_trusted_origin(request: Request) -> None:
    if not origin_ok(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="origin not allowed")
