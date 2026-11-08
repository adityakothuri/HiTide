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
        """No phone numbers, ever."""
        return {"id": self.id, "name": self.name, "age": self.age, "home": {"lat": self.home_lat, "lon": self.home_lon},
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
    def __init__(self, users: Iterable[SafetyUser] = (), registry_path: Path | None = REGISTRY_PATH):
        self._lock = threading.Lock()
        self._users: dict[str, SafetyUser] = {u.id: u for u in users}
        self._path = registry_path
        if registry_path is not None and registry_path.exists():
            try:
                for d in json.loads(registry_path.read_text()):
                    u = _user(d, simulated=False)
                    self._users[u.id] = u
            except (OSError, ValueError, KeyError, TypeError):
                log.exception("could not read %s; enrolled users not loaded", registry_path)

    @classmethod
    def load(cls, path: Path = REGION_USERS_PATH, registry_path: Path | None = REGISTRY_PATH) -> "UserRegistry":
        users: list[SafetyUser] = []
        if path.exists():
            users = [_user(d, simulated=True) for d in json.loads(path.read_text())]
        else:
            log.warning("%s missing: run scripts/gen_region_users.py", path)
        return cls(users, registry_path)

    def get(self, uid: str) -> SafetyUser | None:
        return self._users.get(uid)

    def all(self) -> list[SafetyUser]:
        with self._lock:
            return list(self._users.values())

    def __len__(self) -> int:
        return len(self._users)

    def enroll(self, user: SafetyUser) -> SafetyUser:
        with self._lock:
            existing = self._users.get(user.id)
            if existing is not None and existing.simulated:
                raise ValueError("id belongs to a simulated user")
            self._users[user.id] = user
            if self._path is not None:
                atomic_write_json(self._path, [_to_json(u) for u in self._users.values() if not u.simulated])
        return user

    def phones_of(self, u: SafetyUser) -> list[tuple[str, str]]:
        return [(raw, by) for raw, by in ((u.phone, "driver"), (u.contact_phone, "emergency_contact"),
                                          (u.parent_phone, "parent")) if raw]


def users_to_json(users: Iterable[SafetyUser]) -> list[dict[str, Any]]:
    return [_to_json(u) for u in users]
