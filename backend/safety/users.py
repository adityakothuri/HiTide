"""Opted-in users for the danger pipeline: simulated Kerr County residents plus users enrolled through the API.

data/region_users.json      simulated residents (committed; phones are "sim:<id>" or env:DEMO_PHONE_* refs only)
data/user_registry.json     users enrolled at runtime (gitignored: may hold real phone numbers)
data/safety_state.json      last known position + planned route per user (gitignored)
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.config import DATA_DIR

log = logging.getLogger(__name__)
REGION_USERS_PATH = DATA_DIR / "region_users.json"
REGISTRY_PATH = DATA_DIR / "user_registry.json"
STATE_PATH = DATA_DIR / "safety_state.json"
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
MAX_ENROLLED = 500


def registry_path() -> Path:
    """SAFETY_REGISTRY_PATH overrides (tests, deployments); read at call time."""
    return Path(os.environ.get("SAFETY_REGISTRY_PATH", str(REGISTRY_PATH)))


def state_path() -> Path:
    return Path(os.environ.get("SAFETY_STATE_PATH", str(STATE_PATH)))


@dataclass(frozen=True)
class SafetyUser:
    id: str
    name: str
    age: int | None
    phone: str                         # env:DEMO_PHONE_X | sim:<id> | +E.164 (enrolled, gitignored)
    home_lat: float
    home_lon: float
    contact_name: str | None = None
    contact_phone: str | None = None
    parent_phone: str | None = None
    profile: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = True
    tags: tuple[str, ...] = ()

    @property
    def consented(self) -> bool:
        consent = self.profile.get("consent") if isinstance(self.profile, Mapping) else None
        return isinstance(consent, Mapping) and consent.get("flood_alerts") is True

    def public(self) -> dict[str, Any]:
        """No phone numbers, ever. Real (enrolled) users: first name only, no age, home rounded to ~1 km."""
        if self.simulated:
            name, age, home = self.name, self.age, {"lat": self.home_lat, "lon": self.home_lon}
        else:
            name, age = (self.name.split() or ["user"])[0], None
            home = {"lat": round(self.home_lat, 2), "lon": round(self.home_lon, 2)}
        return {"id": self.id, "name": name, "age": age, "home": home,
                "simulated": self.simulated, "consented": self.consented, "tags": list(self.tags),
                "has_emergency_contact": bool(self.contact_phone), "has_parent": bool(self.parent_phone)}


def _user(d: Mapping[str, Any], simulated: bool) -> SafetyUser:
    return SafetyUser(
        id=str(d["id"]), name=str(d.get("name", d["id"])), age=d.get("age"), phone=str(d.get("phone", f"sim:{d['id']}")),
        home_lat=float(d["home"]["lat"]), home_lon=float(d["home"]["lon"]),
        contact_name=d.get("contact_name"), contact_phone=d.get("contact_phone"), parent_phone=d.get("parent_phone"),
        profile=d.get("profile") or {}, simulated=simulated, tags=tuple(d.get("tags") or ()))


def _to_json(u: SafetyUser) -> dict[str, Any]:
    d = asdict(u)
    d["home"] = {"lat": d.pop("home_lat"), "lon": d.pop("home_lon")}
    d["tags"] = list(u.tags)
    return d


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class UserRegistry:
    def __init__(self, users: Iterable[SafetyUser] = (), registry_path: Path | None = REGISTRY_PATH,
                 store: Any = None):
        self._lock = threading.Lock()
        self._users: dict[str, SafetyUser] = {u.id: u for u in users}
        self._path = registry_path
        self._store = store   # db.store.DataStore: enrollments are written to the primary database
        if registry_path is not None and registry_path.exists():
            try:
                for d in json.loads(registry_path.read_text()):
                    u = _user(d, simulated=False)
                    self._users[u.id] = u
            except (OSError, ValueError, KeyError, TypeError):
                log.exception("could not read %s; enrolled users not loaded", registry_path)

    @classmethod
    def load(cls, path: Path = REGION_USERS_PATH, registry: Path | None | str = "env") -> "UserRegistry":
        """registry="env": SAFETY_REGISTRY_PATH or data/user_registry.json; None: no enrolled users (tests)."""
        users: list[SafetyUser] = []
        if path.exists():
            users = [_user(d, simulated=True) for d in json.loads(path.read_text())]
        else:
            log.warning("%s missing: run scripts/gen_region_users.py", path)
        return cls(users, registry_path() if registry == "env" else (Path(registry) if registry else None))

    @classmethod
    def from_store(cls, store: Any, seed_path: Path = REGION_USERS_PATH) -> "UserRegistry":
        """Users from the primary database (SpacetimeDB app_user + private user_contact/user_profile).
        A fresh, empty database is seeded once from data/region_users.json."""
        rows = store.load_users()
        if not rows and seed_path.exists():
            seed = [{**d, "simulated": True, "population": "region"} for d in json.loads(seed_path.read_text())]
            store.seed_users(seed)
            log.info("seeded %d simulated residents into the %s database", len(seed), store.name)
            rows = store.load_users()
        # The Kerrville drivers (population "kerrville") belong to the town sim, not the Hill Country monitor.
        users = [_user(d, simulated=bool(d.get("simulated", True))) for d in rows
                 if d.get("population", "region") in ("region", "enrolled")]
        return cls(users, registry_path=None, store=store)

    def get(self, uid: str) -> SafetyUser | None:
        return self._users.get(uid)

    def all(self) -> list[SafetyUser]:
        with self._lock:
            return list(self._users.values())

    def __len__(self) -> int:
        return len(self._users)

    def enroll(self, user: SafetyUser) -> SafetyUser:
        """New ids only: an existing user (simulated or enrolled) is never overwritten through the API."""
        with self._lock:
            if user.id in self._users:
                raise ValueError("id already enrolled")
            if sum(1 for u in self._users.values() if not u.simulated) >= MAX_ENROLLED:
                raise OverflowError("enrollment is full")
        if self._store is not None:   # outside the lock (a slow database must not stall the monitor);
            # the database rejects an existing id itself, so a race still can't overwrite anyone
            self._store.enroll_user({**_to_json(user), "simulated": False, "population": "enrolled"})
        with self._lock:
            if user.id in self._users:
                raise ValueError("id already enrolled")
            self._users[user.id] = user
            if self._path is not None:
                atomic_write_json(self._path, [_to_json(u) for u in self._users.values() if not u.simulated])
        return user

    def phones_of(self, u: SafetyUser) -> list[tuple[str, str]]:
        return [(raw, by) for raw, by in ((u.phone, "driver"), (u.contact_phone, "emergency_contact"),
                                          (u.parent_phone, "parent")) if raw]


def users_to_json(users: Iterable[SafetyUser]) -> list[dict[str, Any]]:
    return [_to_json(u) for u in users]
