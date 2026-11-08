"""Minimal SpacetimeDB HTTP client (there is no maintained Python SDK for SpacetimeDB 2.x).

Writes:  POST /v1/database/{db}/call/{reducer}   body: JSON array of arguments in declared order
Reads:   POST /v1/database/{db}/sql              body: SQL text -> [{"schema": ProductType, "rows": [[...], ...]}]

Rows are decoded with their schema: options come back as [0, value] (some) / [1, []] (none) and timestamps as
[[micros]]. Reducer option arguments are sent as {"some": v} / {"none": []} (use `some()` / `NONE`).
Auth: SPACETIME_TOKEN, else the CLI's own login token (~/.config/spacetime/cli.toml). The token is never logged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)
DEFAULT_URL = "http://127.0.0.1:3000"
DEFAULT_DB = "floodwatch"
MAINCLOUD_URL = "https://maincloud.spacetimedb.com"
CLI_CONFIG = Path.home() / ".config" / "spacetime" / "cli.toml"
TIMEOUT_S = 5.0
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NONE: dict[str, list] = {"none": []}


def some(value: Any) -> dict[str, Any]:
    return {"some": value}


def opt(value: Any) -> dict[str, Any]:
    """Python None -> SpacetimeDB none; anything else -> some(value)."""
    return NONE if value is None else some(value)


class SpacetimeError(RuntimeError):
    """A SpacetimeDB request failed (unreachable, rejected by a reducer, or bad SQL)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def quote(value: str) -> str:
    """SQL string literal. The only way values enter SQL text in this codebase."""
    if not isinstance(value, str):
        raise TypeError("quote() takes a string")
    if "\x00" in value:
        raise ValueError("NUL byte in SQL value")
    return "'" + value.replace("'", "''") + "'"


def ident(name: str) -> str:
    """A table or column name; only plain identifiers are allowed (never user input)."""
    if not _IDENT.match(name):
        raise ValueError(f"bad SQL identifier {name!r}")
    return name


def _token_from_cli() -> str | None:
    try:
        return tomllib.loads(CLI_CONFIG.read_text()).get("spacetimedb_token")
    except (OSError, tomllib.TOMLDecodeError):
        return None


@dataclass(frozen=True)
class SpacetimeConfig:
    url: str
    database: str
    token: str | None

    @classmethod
    def from_env(cls) -> "SpacetimeConfig":
        server = os.environ.get("SPACETIME_SERVER", "local")
        url = os.environ.get("SPACETIME_URL") or (MAINCLOUD_URL if server == "maincloud" else DEFAULT_URL)
        return cls(url.rstrip("/"), os.environ.get("SPACETIME_DB", DEFAULT_DB),
                   os.environ.get("SPACETIME_TOKEN") or _token_from_cli())

    def public(self) -> dict[str, Any]:
        return {"url": self.url, "database": self.database, "authenticated": bool(self.token)}


# ---- decoding ------------------------------------------------------------------
def _is_option(t: dict) -> bool:
    variants = t.get("Sum", {}).get("variants") if isinstance(t, dict) else None
    return bool(variants) and [v.get("name", {}).get("some") for v in variants] == ["some", "none"]


def _is_timestamp(t: dict) -> bool:
    elems = t.get("Product", {}).get("elements") if isinstance(t, dict) else None
    return bool(elems) and len(elems) == 1 and elems[0].get("name", {}).get("some") == "__timestamp_micros_since_unix_epoch__"


def decode_value(t: dict, v: Any) -> Any:
    if _is_option(t):
        if not isinstance(v, list) or len(v) != 2:
            raise SpacetimeError(f"bad option value {v!r}")
        return None if v[0] == 1 else decode_value(t["Sum"]["variants"][0]["algebraic_type"], v[1])
    if _is_timestamp(t):
        return v[0] / 1e6   # epoch seconds
    if isinstance(t, dict) and "Array" in t and isinstance(v, list):
        return [decode_value(t["Array"], x) for x in v]
    return v


def decode_rows(result: dict) -> list[dict[str, Any]]:
    elems = result["schema"]["elements"]
    names = [e["name"]["some"] for e in elems]
    types = [e["algebraic_type"] for e in elems]
    return [{n: decode_value(tp, v) for n, tp, v in zip(names, types, row)} for row in result["rows"]]


# ---- client ----------------------------------------------------------------------
class SpacetimeClient:
    """Thread-safe (httpx.Client is). One instance per process."""

    def __init__(self, config: SpacetimeConfig | None = None, transport: httpx.BaseTransport | None = None,
                 timeout_s: float = TIMEOUT_S):
        self.config = config or SpacetimeConfig.from_env()
        headers = {"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}
        self._http = httpx.Client(base_url=self.config.url, headers=headers, timeout=timeout_s, transport=transport)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, **kw: Any) -> httpx.Response:
        # Retry only when the request never reached the server (connect failure). A timeout after sending may
        # have committed, and repeating a reducer (enroll, record_ingestion) would duplicate it.
        try:
            return self._http.post(path, **kw)
        except httpx.ConnectError:
            pass
        except httpx.TransportError as exc:
            raise SpacetimeError(f"SpacetimeDB request failed at {self.config.url}: {type(exc).__name__}") from exc
        try:
            return self._http.post(path, **kw)
        except httpx.TransportError as exc:
            raise SpacetimeError(f"SpacetimeDB unreachable at {self.config.url}: {type(exc).__name__}") from exc

    def call(self, reducer: str, *args: Any) -> None:
        """Run one reducer (one transaction). Raises SpacetimeError with the reducer's message on rejection."""
        r = self._post(f"/v1/database/{self.config.database}/call/{ident(reducer)}",
                       content=json.dumps(list(args), allow_nan=False), headers={"content-type": "application/json"})
        if r.status_code >= 400:
            raise SpacetimeError(f"{reducer} rejected ({r.status_code}): {r.text.strip()[:300]}", r.status_code)

    def sql(self, query: str) -> list[dict[str, Any]]:
        """One SELECT -> list of dict rows (decoded)."""
        r = self._post(f"/v1/database/{self.config.database}/sql", content=query.encode())
        if r.status_code >= 400:
            raise SpacetimeError(f"SQL failed ({r.status_code}): {r.text.strip()[:300]}", r.status_code)
        results = r.json()
        return decode_rows(results[0]) if results else []

    def ping(self) -> bool:
        try:
            return self._http.get("/v1/ping").status_code == 200
        except httpx.TransportError:
            return False

    def database_exists(self) -> bool:
        """Published AND we are the owner: `config` is private, so only the owner's token can read it."""
        try:
            return bool(self.sql("SELECT * FROM config"))
        except SpacetimeError:
            return False
