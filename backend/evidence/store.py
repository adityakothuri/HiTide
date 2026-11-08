"""SQLite evidence store. Non-destructive migrations and append-only observations.

SQLite makes the hackathon run without a database server. Spatial analysis is done
on the existing road graph; a future PostGIS backend can implement this interface.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from evidence.models import ObservationIn, now_iso

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "floodwatch.sqlite3"
SOURCES = [
    ("nws_alerts", "National Weather Service", "warning", "https://www.weather.gov/documentation/services-web-alerts", 120),
    ("usgs_gage", "USGS Guadalupe River at Kerrville", "gauge", "https://api.waterdata.usgs.gov/docs/ogcapi", 300),
    ("usgs_flood_impacts", "USGS flood impact reference points", "context", "https://api.waterdata.usgs.gov/rtfi-api/docs", 900),
    ("drivetexas", "TxDOT DriveTexas", "closure", "https://api.drivetexas.org/api-docs", 300),
    ("local_reports", "Local and community reports", "report", "Operator submissions", 300),
    ("drone", "Drone inspections", "drone", "Mission evidence", 300),
]


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def prepare_observation(observation: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Validate and hash an observation. Shared by every evidence backend so they dedupe identically."""
    body = ObservationIn.model_validate(observation).model_dump()
    semantic = {key: value for key, value in body.items()
                if key not in {"id", "ingested_at", "supersedes_id", "source_mode"}}
    # Raw provider data is evidence, but fetch transport metadata is not a revision.
    semantic["raw"] = {key: value for key, value in body["raw"].items()
                       if key not in {"fetched_at", "ingested_at", "retrieved_at", "source_mode"}}
    return body, hashlib.sha256(encoded(semantic).encode()).hexdigest()


def raw_hash(raw: Any) -> tuple[str, str]:
    raw_json = encoded(raw)
    return raw_json, hashlib.sha256(raw_json.encode()).hexdigest()


class Store:
    def __init__(self, path: str | Path | None = None):
        selected = str(path if path is not None else os.environ.get("HITIDE_DB_PATH") or os.environ.get("FLOODWATCH_DB_PATH", DEFAULT_DB))
        if selected != ":memory:":
            Path(selected).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.path = selected
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self.conn = sqlite3.connect(selected, check_same_thread=False, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self.conn:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError(f"Database schema {version} is newer than this application supports")
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                    attribution TEXT NOT NULL, expected_update_s INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS raw_records (
                    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    received_at TEXT NOT NULL, UNIQUE(source_id, payload_hash));
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    source_record_id TEXT NOT NULL, observed_at TEXT,
                    ingested_at TEXT NOT NULL, semantic_hash TEXT NOT NULL UNIQUE,
                    supersedes_id TEXT REFERENCES observations(id),
                    raw_record_id INTEGER NOT NULL REFERENCES raw_records(id), body_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS observation_source_record ON observations(source_id, source_record_id);
                CREATE INDEX IF NOT EXISTS observation_supersedes ON observations(supersedes_id);
                CREATE INDEX IF NOT EXISTS observation_raw_record ON observations(raw_record_id);
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    status TEXT NOT NULL, detail TEXT NOT NULL, fetched_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ingestion_source ON ingestion_runs(source_id,id);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, body_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS inspection_tasks (id TEXT PRIMARY KEY, body_json TEXT NOT NULL);
            """)
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(ingestion_runs)")}
            if "attempted_at" not in columns:
                self.conn.execute("ALTER TABLE ingestion_runs ADD COLUMN attempted_at TEXT NOT NULL DEFAULT ''")
                self.conn.execute("UPDATE ingestion_runs SET attempted_at=fetched_at WHERE attempted_at=''")
            self.conn.execute("PRAGMA user_version=2")
            self.conn.executemany("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)", SOURCES)

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    @contextmanager
    def transaction(self):
        """Compose several writes atomically; nested writes use savepoints."""
        with self._lock:
            depth = self._transaction_depth
            savepoint = f"evidence_{depth}"
            if depth == 0:
                self.conn.execute("BEGIN IMMEDIATE")
            else:
                self.conn.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
            try:
                yield self
            except BaseException:
                if depth == 0:
                    self.conn.rollback()
                else:
                    self.conn.execute(f"ROLLBACK TO {savepoint}")
                    self.conn.execute(f"RELEASE {savepoint}")
                raise
            else:
                if depth == 0:
                    self.conn.commit()
                else:
                    self.conn.execute(f"RELEASE {savepoint}")
            finally:
                self._transaction_depth -= 1

    def _source(self, source_id: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)",
                          (source_id, source_id.replace("_", " "), "report", "Submitted evidence", 300))

    def add_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        body, semantic_hash = prepare_observation(observation)
        with self.transaction():
            prior = self.conn.execute("SELECT body_json FROM observations WHERE semantic_hash=?", (semantic_hash,)).fetchone()
            if prior:
                return json.loads(prior[0])
            self._source(body["source_id"])
            latest = self.conn.execute("SELECT id FROM observations WHERE source_id=? AND source_record_id=? ORDER BY rowid DESC LIMIT 1",
                                       (body["source_id"], body["source_record_id"])).fetchone()
            if body["supersedes_id"] and (latest is None or body["supersedes_id"] != latest[0]):
                raise ValueError("supersedes_id must identify the latest revision of the same source record")
            body["id"] = body["id"] or f"obs-{uuid.uuid4().hex}"
            body["ingested_at"] = now_iso()  # the server owns receipt time
            body["supersedes_id"] = body["supersedes_id"] or (latest[0] if latest else None)
            raw_json, payload_hash = raw_hash(body["raw"])
            self.conn.execute("INSERT OR IGNORE INTO raw_records(source_id,payload_json,payload_hash,received_at) VALUES (?,?,?,?)",
                              (body["source_id"], raw_json, payload_hash, body["ingested_at"]))
            raw_id = self.conn.execute("SELECT id FROM raw_records WHERE source_id=? AND payload_hash=?", (body["source_id"], payload_hash)).fetchone()[0]
            self.conn.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)",
                              (body["id"], body["source_id"], body["source_record_id"], body["observed_at"], body["ingested_at"],
                               semantic_hash, body["supersedes_id"], raw_id, encoded(body)))
        return body

    def list_observations(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(row[0]) for row in self.conn.execute("SELECT body_json FROM observations ORDER BY rowid")]

    def list_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute("""SELECT s.*, r.status, r.detail, NULLIF(r.fetched_at,'') AS fetched_at,
                r.attempted_at AS last_attempt_at,
                (SELECT i.fetched_at FROM ingestion_runs i WHERE i.source_id=s.id AND i.status='live'
                 ORDER BY i.id DESC LIMIT 1) AS last_successful_fetch_at FROM sources s
                LEFT JOIN ingestion_runs r ON r.id=(SELECT MAX(i.id) FROM ingestion_runs i WHERE i.source_id=s.id)
                ORDER BY s.id""").fetchall()
            return [{**dict(row), "status": row["status"] or "not_fetched"} for row in rows]

    def record_ingestion(self, source_id: str, status: str, detail: str = "", fetched_at: str | None = None) -> None:
        with self.transaction():
            self._source(source_id)
            self.conn.execute("INSERT INTO ingestion_runs(source_id,status,detail,fetched_at,attempted_at) VALUES (?,?,?,?,?)",
                              (source_id, status, detail, fetched_at or (now_iso() if status == "live" else ""), now_iso()))

    def get_dataset(self) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute("SELECT body_json FROM settings WHERE key='dataset'").fetchone()
            return json.loads(row[0]) if row else None

    def set_dataset(self, dataset: dict[str, Any]) -> None:
        with self.transaction():
            self.conn.execute("INSERT INTO settings VALUES ('dataset',?) ON CONFLICT(key) DO UPDATE SET body_json=excluded.body_json", (encoded(dataset),))

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(row[0]) for row in self.conn.execute("SELECT body_json FROM inspection_tasks ORDER BY id")]

    def save_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if not task.get("id"):
            raise ValueError("inspection task requires an id")
        with self.transaction():
            self.conn.execute("INSERT INTO inspection_tasks VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body_json=excluded.body_json", (task["id"], encoded(task)))
        return task

    def diagnostics(self) -> dict[str, Any]:
        """Read-only health checks: never delete or reset an existing database."""
        with self._lock:
            integrity = [row[0] for row in self.conn.execute("PRAGMA integrity_check")]
            foreign_keys = [tuple(row) for row in self.conn.execute("PRAGMA foreign_key_check")]
            return {"path": self.path, "schema_version": self.conn.execute("PRAGMA user_version").fetchone()[0],
                    "integrity": integrity, "foreign_key_errors": foreign_keys,
                    "ok": integrity == ["ok"] and not foreign_keys,
                    "observation_count": self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
                    "raw_record_count": self.conn.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]}

    def health(self) -> dict[str, Any]:
        return self.diagnostics()
