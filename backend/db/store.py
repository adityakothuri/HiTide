"""DataStore: everything the backend persists outside the evidence store.

Three implementations share one interface:
  SpacetimeDataStore  primary (SpacetimeDB reducers + SQL)
  FileDataStore       fallback when SpacetimeDB is unreachable (today's JSON/JSONL files)
  MemoryDataStore     tests

Runtime writes go through `WriteBehind`, a single background thread with a bounded queue, so a slow or
unreachable database never blocks the event loop or a simulation step. Startup reads are synchronous.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from app.config import DATA_DIR
from db.spacetime import SpacetimeClient, SpacetimeError, ident, quote

log = logging.getLogger(__name__)
REGION_USERS_PATH = DATA_DIR / "region_users.json"
BATCH = 200
QUEUE_MAX = 20_000
BREAKER_S = 15   # after a failed write, skip remote writes this long (fail fast to the fallbacks)


class DataStore(Protocol):
    name: str

    def load_users(self) -> list[dict[str, Any]]: ...
    def seed_users(self, users: list[dict[str, Any]]) -> None: ...
    def enroll_user(self, user: dict[str, Any]) -> None: ...
    def load_tracks(self) -> dict[str, dict[str, Any]]: ...
    def save_tracks(self, rows: list[dict[str, Any]]) -> None: ...
    def load_responses(self) -> dict[str, dict[str, Any]]: ...
    def save_responses(self, rows: list[dict[str, Any]]) -> None: ...
    def save_dangers(self, rows: list[dict[str, Any]]) -> None: ...
    def append_outreach(self, events: list[dict[str, Any]]) -> None: ...
    def list_outreach(self, limit: int = 500) -> list[dict[str, Any]]: ...
    def save_case(self, case: dict[str, Any]) -> None: ...
    def list_cases(self) -> list[dict[str, Any]]: ...
    def add_snapshot(self, snap: dict[str, Any]) -> None: ...
    def list_snapshots(self) -> list[dict[str, Any]]: ...
    def kv_get(self, key: str) -> str | None: ...
    def kv_set(self, key: str, value: str) -> None: ...
    def wipe_runtime(self, scope: str) -> None: ...
    def counts(self) -> dict[str, int]: ...


def _chunks(rows: list[Any], n: int = BATCH) -> Iterable[list[Any]]:
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def public_user_row(u: dict[str, Any]) -> dict[str, Any]:
    """The reducer payload for a user: full private data plus the public projection (privacy rule in one place)."""
    simulated = bool(u.get("simulated", True))
    home = u["home"]
    first = (str(u.get("name") or u["id"]).split() or [u["id"]])[0]
    return {
        "id": u["id"], "name": u.get("name", u["id"]), "age": u.get("age"),
        "home_lat": home["lat"], "home_lon": home["lon"],
        "simulated": simulated, "consented": bool((u.get("profile") or {}).get("consent", {}).get("flood_alerts")),
        "population": u.get("population", "region" if simulated else "enrolled"),
        "tags": list(u.get("tags") or []) if simulated else [],   # public table: nothing extra about real people
        "public_name": u.get("name", u["id"]) if simulated else first,
        "public_age": u.get("age") if simulated else None,
        "public_lat": home["lat"] if simulated else round(home["lat"], 2),
        "public_lon": home["lon"] if simulated else round(home["lon"], 2),
        "phone": u.get("phone") or f"sim:{u['id']}", "contact_name": u.get("contact_name"),
        "contact_phone": u.get("contact_phone"), "parent_phone": u.get("parent_phone"), "profile": u.get("profile") or {},
    }


# ---- SpacetimeDB ------------------------------------------------------------------
def count(client: SpacetimeClient, table: str) -> int:
    rows = client.sql(f"SELECT COUNT(*) AS n FROM {ident(table)}")
    return int(rows[0]["n"]) if rows else 0


class SpacetimeDataStore:
    name = "spacetime"

    def __init__(self, client: SpacetimeClient):
        self.c = client

    def load_users(self) -> list[dict[str, Any]]:
        pub = {r["id"]: r for r in self.c.sql("SELECT id, simulated, population, tags_json FROM app_user")}
        contacts = {r["user_id"]: r for r in self.c.sql("SELECT * FROM user_contact")}
        profiles = {r["user_id"]: r for r in self.c.sql("SELECT * FROM user_profile")}
        out = []
        for uid, p in pub.items():
            c = contacts.get(uid)
            if c is None:
                continue
            out.append({"id": uid, "name": c["full_name"], "age": c["age"], "phone": c["phone"],
                        "home": {"lat": c["home_lat"], "lon": c["home_lon"]}, "contact_name": c["contact_name"],
                        "contact_phone": c["contact_phone"], "parent_phone": c["parent_phone"],
                        "profile": json.loads(profiles[uid]["profile_json"]) if uid in profiles else {},
                        "tags": json.loads(p["tags_json"]), "simulated": p["simulated"], "population": p["population"]})
        return sorted(out, key=lambda u: u["id"])

    def seed_users(self, users: list[dict[str, Any]]) -> None:
        for chunk in _chunks([public_user_row(u) for u in users], 100):
            self.c.call("upsert_users", json.dumps(chunk))

    def enroll_user(self, user: dict[str, Any]) -> None:
        try:
            self.c.call("enroll_user", json.dumps(public_user_row(user)))
        except SpacetimeError as exc:
            if "already enrolled" in str(exc):
                raise ValueError("id already enrolled") from exc
            raise

    def load_tracks(self) -> dict[str, dict[str, Any]]:
        return {r["user_id"]: {"motion": json.loads(r["motion_json"]), "route": json.loads(r["route_json"]),
                               "pinged": r["pinged"]} for r in self.c.sql("SELECT * FROM user_track")}

    def save_tracks(self, rows: list[dict[str, Any]]) -> None:
        for chunk in _chunks(rows):
            self.c.call("upsert_tracks", json.dumps(chunk))

    def load_responses(self) -> dict[str, dict[str, Any]]:
        return {r["user_id"]: json.loads(r["state_json"]) for r in self.c.sql("SELECT * FROM response_state")}

    def save_responses(self, rows: list[dict[str, Any]]) -> None:
        for chunk in _chunks(rows):
            self.c.call("upsert_responses", json.dumps(chunk))

    def save_dangers(self, rows: list[dict[str, Any]]) -> None:
        for chunk in _chunks(rows):
            self.c.call("upsert_dangers", json.dumps(chunk))

    def append_outreach(self, events: list[dict[str, Any]]) -> None:
        for chunk in _chunks(events):
            self.c.call("log_outreach", json.dumps(chunk))

    def list_outreach(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.c.sql("SELECT * FROM outreach_event")
        return sorted(rows, key=lambda r: r["ts"])[-limit:]

    def save_case(self, case: dict[str, Any]) -> None:
        self.c.call("upsert_case", case["id"], str(case.get("driver_id", "")), str(case.get("state", "")), json.dumps(case))

    def list_cases(self) -> list[dict[str, Any]]:
        return [json.loads(r["body_json"]) for r in self.c.sql("SELECT body_json FROM escalation_case")]

    def add_snapshot(self, snap: dict[str, Any]) -> None:
        sid = snap.get("id") or f"{snap.get('point_id')}:{snap.get('drone_id')}:{snap.get('time')}"
        self.c.call("add_snapshot", str(sid), str(snap.get("point_id", "")), str(snap.get("drone_id", "")),
                    str(snap.get("time", "")), json.dumps(snap, default=str))

    def list_snapshots(self) -> list[dict[str, Any]]:
        return [json.loads(r["body_json"]) for r in self.c.sql("SELECT body_json FROM vision_snapshot")]

    def kv_get(self, key: str) -> str | None:
        rows = self.c.sql(f"SELECT value FROM kv WHERE key = {quote(key)}")
        return rows[0]["value"] if rows else None

    def kv_set(self, key: str, value: str) -> None:
        self.c.call("kv_set", key, value)

    def wipe_runtime(self, scope: str) -> None:
        self.c.call("wipe_runtime", scope)

    def counts(self) -> dict[str, int]:
        out = {}
        for table in ("app_user", "user_track", "response_state", "danger_latest", "outreach_event",
                      "escalation_case", "vision_snapshot", "observation", "inspection_task"):
            out[table] = count(self.c, table)
        return out


# ---- memory (tests) and files (fallback) -------------------------------------------------
class MemoryDataStore:
    name = "memory"

    def __init__(self, users: list[dict[str, Any]] | None = None):
        self.users: dict[str, dict[str, Any]] = {u["id"]: dict(u) for u in (users or [])}
        self.tracks: dict[str, dict[str, Any]] = {}
        self.responses: dict[str, dict[str, Any]] = {}
        self.dangers: dict[str, dict[str, Any]] = {}
        self.outreach: list[dict[str, Any]] = []
        self.cases: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.kv: dict[str, str] = {}
        self._lock = threading.Lock()

    def load_users(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(u) for _, u in sorted(self.users.items())]

    def seed_users(self, users: list[dict[str, Any]]) -> None:
        with self._lock:
            for u in users:
                self.users[u["id"]] = dict(u)

    def enroll_user(self, user: dict[str, Any]) -> None:
        with self._lock:
            if user["id"] in self.users:
                raise ValueError("id already enrolled")
            self.users[user["id"]] = dict(user)

    def load_tracks(self) -> dict[str, dict[str, Any]]:
        return dict(self.tracks)

    def save_tracks(self, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            for r in rows:
                self.tracks[r["user_id"]] = {k: v for k, v in r.items() if k != "user_id"}

    def load_responses(self) -> dict[str, dict[str, Any]]:
        return {k: v["state"] for k, v in self.responses.items()}

    def save_responses(self, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            for r in rows:
                self.responses[r["user_id"]] = r

    def save_dangers(self, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            for r in rows:
                self.dangers[r["user_id"]] = r

    def append_outreach(self, events: list[dict[str, Any]]) -> None:
        with self._lock:
            seen = {e["id"] for e in self.outreach}
            for e in events:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    self.outreach.append(e)

    def list_outreach(self, limit: int = 500) -> list[dict[str, Any]]:
        return sorted(self.outreach, key=lambda e: e.get("ts", ""))[-limit:]

    def save_case(self, case: dict[str, Any]) -> None:
        with self._lock:
            self.cases[case["id"]] = case

    def list_cases(self) -> list[dict[str, Any]]:
        return list(self.cases.values())

    def add_snapshot(self, snap: dict[str, Any]) -> None:
        with self._lock:
            sid = snap.get("id") or f"{snap.get('point_id')}:{snap.get('drone_id')}:{snap.get('time')}"
            self.snapshots[str(sid)] = snap

    def list_snapshots(self) -> list[dict[str, Any]]:
        return list(self.snapshots.values())

    def kv_get(self, key: str) -> str | None:
        return self.kv.get(key)

    def kv_set(self, key: str, value: str) -> None:
        self.kv[key] = value

    def wipe_runtime(self, scope: str) -> None:
        with self._lock:
            if scope in ("safety", "all_runtime"):
                self.tracks, self.responses, self.dangers = {}, {}, {}
            if scope in ("cases", "all_runtime"):
                self.cases = {}
            if scope in ("outreach", "all_runtime"):
                self.outreach = []

    def counts(self) -> dict[str, int]:
        return {"app_user": len(self.users), "user_track": len(self.tracks), "response_state": len(self.responses),
                "danger_latest": len(self.dangers), "outreach_event": len(self.outreach),
                "escalation_case": len(self.cases), "vision_snapshot": len(self.snapshots)}


class FileDataStore(MemoryDataStore):
    """Fallback: users from data/region_users.json (+ the gitignored registry), outreach appended to the JSONL log.
    Everything else stays in memory, as before SpacetimeDB."""

    name = "file"

    def __init__(self, region_users: Path = REGION_USERS_PATH, registry: Path | None = None, log_path: Path | None = None):
        users = json.loads(region_users.read_text()) if region_users.exists() else []
        for u in users:
            u.setdefault("simulated", True)
        super().__init__(users)
        self.registry = registry
        self.log_path = log_path
        if registry is not None and registry.exists():
            for u in json.loads(registry.read_text()):
                self.users[u["id"]] = {**u, "simulated": False}

    def enroll_user(self, user: dict[str, Any]) -> None:
        super().enroll_user(user)
        if self.registry is not None:
            from safety.users import atomic_write_json
            atomic_write_json(self.registry, [u for u in self.users.values() if not u.get("simulated", True)])

    def append_outreach(self, events: list[dict[str, Any]]) -> None:
        if self.log_path is not None:
            from outreach.log import append_log
            for e in events:
                append_log(e, self.log_path)


# ---- write-behind ---------------------------------------------------------------------------
class WriteBehind:
    """Run datastore writes on one background thread, in order. Never blocks or raises in the caller."""

    def __init__(self, name: str = "db-writer"):
        self._q: queue.Queue[tuple[Callable[[], None], Callable[[], None] | None] | None] = queue.Queue(maxsize=QUEUE_MAX)
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()
        self.failed = 0
        self.dropped = 0
        self.last_error: str | None = None
        self._open_until = 0.0

    def submit(self, fn: Callable[[], None], on_fail: Callable[[], None] | None = None) -> None:
        """Queue a write. `on_fail` runs (on the writer thread) if the write fails, is skipped while the
        database is down, or is dropped because the queue is full, so callers can keep a local copy or retry."""
        try:
            self._q.put_nowait((fn, on_fail))
        except queue.Full:
            self.dropped += 1
            if self.dropped % 1000 == 1:
                log.error("database write queue full; dropped %d writes", self.dropped)
            _safe(on_fail)

    def _run(self) -> None:
        while True:
            item = self._q.get()
            try:
                if item is None:
                    return
                fn, on_fail = item
                if time.monotonic() < self._open_until:   # circuit open: the database just failed; don't wait on it
                    self.failed += 1
                    _safe(on_fail)
                    continue
                fn()
            except Exception as exc:  # a failed write is logged, never fatal
                self.failed += 1
                self.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                if isinstance(exc, SpacetimeError) and exc.status is None:   # unreachable, not a rejected write
                    self._open_until = time.monotonic() + BREAKER_S
                    log.error("database unreachable (pausing remote writes %ds): %s", BREAKER_S, self.last_error)
                else:
                    log.error("database write failed: %s", self.last_error)
                _safe(item[1] if item else None)
            finally:
                self._q.task_done()

    def flush(self, timeout_s: float = 10.0) -> bool:
        """Wait until queued writes are done (shutdown, tests)."""
        done = threading.Event()
        self.submit(done.set, on_fail=done.set)
        return done.wait(timeout_s)

    def close(self) -> None:
        self.flush()
        try:
            self._q.put(None, timeout=5)
        except queue.Full:
            log.error("database writer did not drain before shutdown; %d writes lost", self._q.qsize())
            return
        self._thread.join(timeout=5)

    def stats(self) -> dict[str, Any]:
        return {"queued": self._q.qsize(), "failed": self.failed, "dropped": self.dropped, "last_error": self.last_error,
                "paused": time.monotonic() < self._open_until}


def _safe(fn: Callable[[], None] | None) -> None:
    if fn is None:
        return
    try:
        fn()
    except Exception:
        log.exception("database write fallback failed")
