"""Pick the database. SpacetimeDB is the primary; SQLite + files is the loud fallback.

HITIDE_DB_BACKEND:
  spacetime (default)  SpacetimeDB at SPACETIME_URL / SPACETIME_DB. If it is unreachable or the module isn't
                       published, log an ERROR and fall back to SQLite + files (the app keeps working).
  sqlite               evidence in SQLite, users/outreach in files, the rest in memory (no SpacetimeDB).
  mongodb              evidence in MongoDB (MONGODB_URI), the rest like sqlite.
  memory               everything in memory (tests).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from db.spacetime import SpacetimeClient, SpacetimeConfig
from db.store import DataStore, FileDataStore, MemoryDataStore, SpacetimeDataStore, WriteBehind

log = logging.getLogger(__name__)
BACKENDS = ("spacetime", "sqlite", "mongodb", "memory")


@dataclass
class Database:
    backend: str                       # what is actually in use
    requested: str                     # what HITIDE_DB_BACKEND asked for
    evidence: Any                      # Store-compatible evidence store
    data: DataStore
    writer: WriteBehind
    fallback_reason: str | None = None
    client: SpacetimeClient | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return self.backend if not self.fallback_reason else f"{self.backend} (fallback: {self.fallback_reason})"

    def public(self) -> dict[str, Any]:
        return {"backend": self.backend, "requested": self.requested, "fallback_reason": self.fallback_reason,
                "writes": self.writer.stats(), **self.details}

    def close(self) -> None:
        self.writer.close()
        try:
            self.evidence.close()
        finally:
            if self.client is not None:
                self.client.close()


def requested_backend() -> str:
    value = os.environ.get("HITIDE_DB_BACKEND", "spacetime").strip().lower()
    if value not in BACKENDS:
        raise ValueError(f"HITIDE_DB_BACKEND must be one of {BACKENDS}, got {value!r}")
    return value


def _sqlite(requested: str, reason: str | None) -> Database:
    from evidence.store import Store
    from outreach.log import DEFAULT_LOG_PATH
    from safety.users import registry_path
    return Database("sqlite", requested, Store(), FileDataStore(registry=registry_path(), log_path=DEFAULT_LOG_PATH),
                    WriteBehind(), reason)


def open_database(requested: str | None = None) -> Database:
    requested = requested or requested_backend()
    if requested == "memory":
        from evidence.store import Store
        return Database("memory", requested, Store(":memory:"), MemoryDataStore(), WriteBehind())
    if requested == "mongodb":
        from evidence.mongo_store import MongoStore
        from outreach.log import DEFAULT_LOG_PATH
        from safety.users import registry_path
        evidence = MongoStore(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?replicaSet=floodwatch"),
                              os.environ.get("MONGODB_DATABASE", "floodwatch"))
        return Database("mongodb", requested, evidence,
                        FileDataStore(registry=registry_path(), log_path=DEFAULT_LOG_PATH), WriteBehind())
    if requested == "sqlite":
        return _sqlite(requested, None)
    cfg = SpacetimeConfig.from_env()
    client = SpacetimeClient(cfg)
    if not client.ping():
        client.close()
        reason = f"SpacetimeDB unreachable at {cfg.url}"
        log.error("%s; FALLING BACK TO SQLITE. Start it with scripts/spacetime_up.sh", reason)
        return _sqlite(requested, reason)
    if not client.database_exists():
        client.close()
        reason = f"database '{cfg.database}' not published (or token lacks access) at {cfg.url}"
        log.error("%s; FALLING BACK TO SQLITE. Publish with scripts/spacetime_up.sh", reason)
        return _sqlite(requested, reason)
    from db.evidence import SpacetimeEvidenceStore
    log.info("SpacetimeDB primary database: %s/%s", cfg.url, cfg.database)
    return Database("spacetime", requested, SpacetimeEvidenceStore(client), SpacetimeDataStore(client), WriteBehind(),
                    client=client, details={"spacetime": cfg.public()})
