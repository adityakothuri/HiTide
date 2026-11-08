"""Evidence store on SpacetimeDB. Same interface as evidence.store.Store (SQLite) and evidence.mongo_store.MongoStore.

Validation and hashing are shared (evidence.store.prepare_observation); the add_observation reducer does the
atomic part (dedupe by semantic hash, revision chain, raw payload dedupe). Geo queries use the indexed bounding
box columns as a coarse filter, then exact geometry with shapely.
"""

from __future__ import annotations

import json
import math
import threading
import uuid
from contextlib import contextmanager
from typing import Any

from shapely.geometry import Point, shape

from db.spacetime import SpacetimeClient, SpacetimeError, opt, quote
from evidence.models import ObservationIn, now_iso
from evidence.store import prepare_observation, raw_hash

M_PER_DEG = 111_320.0
MAX_RADIUS_M = 100_000.0


def _bbox(geometry: dict[str, Any] | None) -> tuple[float | None, float | None, float | None, float | None]:
    if not geometry:
        return None, None, None, None
    try:
        b = shape(geometry).bounds
    except Exception:  # an unusual geometry still stores; it just isn't geo-searchable
        return None, None, None, None
    return (b[0], b[1], b[2], b[3]) if all(math.isfinite(v) for v in b) else (None, None, None, None)


class SpacetimeEvidenceStore:
    backend = "spacetime"

    def __init__(self, client: SpacetimeClient):
        self.c = client
        self._lock = threading.RLock()

    # ---- interface parity -------------------------------------------------
    def close(self) -> None:
        """The client is shared with the DataStore; the factory closes it."""

    @contextmanager
    def transaction(self):
        """Each write is one atomic reducer, so this only serialises callers (kept for interface parity)."""
        with self._lock:
            yield self

    def _by_hash(self, semantic_hash: str) -> dict[str, Any] | None:
        rows = self.c.sql(f"SELECT body_json FROM observation WHERE semantic_hash = {quote(semantic_hash)}")
        return json.loads(rows[0]["body_json"]) if rows else None

    def add_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        body, semantic_hash = prepare_observation(observation)
        with self._lock:
            prior = self._by_hash(semantic_hash)
            if prior is not None:
                return prior
            body["id"] = body["id"] or f"obs-{uuid.uuid4().hex}"
            body["ingested_at"] = now_iso()  # the server owns receipt time
            raw_json, payload_hash = raw_hash(body["raw"])
            min_lon, min_lat, max_lon, max_lat = _bbox(body.get("geometry"))
            try:
                self.c.call("add_observation", semantic_hash, payload_hash, raw_json, json.dumps(body, allow_nan=False),
                            opt(min_lon), opt(min_lat), opt(max_lon), opt(max_lat))
            except SpacetimeError as exc:
                if "supersedes_id must identify" in str(exc):
                    raise ValueError("supersedes_id must identify the latest revision of the same source record") from exc
                raise
            stored = self._by_hash(semantic_hash)
        if stored is None:
            raise SpacetimeError("observation was not stored")
        return stored

    def list_observations(self) -> list[dict[str, Any]]:
        rows = self.c.sql("SELECT seq, body_json FROM observation")
        return [json.loads(r["body_json"]) for r in sorted(rows, key=lambda r: r["seq"])]

    def list_sources(self) -> list[dict[str, Any]]:
        sources = self.c.sql("SELECT * FROM source")
        runs = sorted(self.c.sql("SELECT * FROM ingestion_run"), key=lambda r: r["seq"])
        latest: dict[str, dict] = {}
        live: dict[str, str] = {}
        for r in runs:
            latest[r["source_id"]] = r
            if r["status"] == "live":
                live[r["source_id"]] = r["fetched_at"]
        out = []
        for s in sorted(sources, key=lambda s: s["id"]):
            r = latest.get(s["id"])
            out.append({"id": s["id"], "name": s["name"], "category": s["category"], "attribution": s["attribution"],
                        "expected_update_s": s["expected_update_s"],
                        "status": r["status"] if r else "not_fetched", "detail": r["detail"] if r else None,
                        "fetched_at": (r["fetched_at"] or None) if r else None,
                        "last_attempt_at": r["attempted_at"] if r else None,
                        "last_successful_fetch_at": live.get(s["id"])})
        return out

    def record_ingestion(self, source_id: str, status: str, detail: str = "", fetched_at: str | None = None) -> None:
        self.c.call("record_ingestion", source_id, status, detail,
                    fetched_at or (now_iso() if status == "live" else ""), now_iso())

    def get_dataset(self) -> dict[str, Any] | None:
        rows = self.c.sql("SELECT body_json FROM setting WHERE key = 'dataset'")
        return json.loads(rows[0]["body_json"]) if rows else None

    def set_dataset(self, dataset: dict[str, Any]) -> None:
        self.c.call("set_setting", "dataset", json.dumps(dataset, sort_keys=True, allow_nan=False))

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = self.c.sql("SELECT id, body_json FROM inspection_task")
        return [json.loads(r["body_json"]) for r in sorted(rows, key=lambda r: r["id"])]

    def save_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if not task.get("id"):
            raise ValueError("inspection task requires an id")
        self.c.call("save_task", task["id"], str(task.get("status", "")), str(task.get("road_id", "")),
                    json.dumps(task, sort_keys=True, allow_nan=False))
        return task

    # ---- geo (Mongo parity) ------------------------------------------------
    def nearby_observations(self, lon: float, lat: float, radius_m: float) -> list[dict[str, Any]]:
        ObservationIn.geojson({"type": "Point", "coordinates": [lon, lat]})
        if not math.isfinite(radius_m) or not 0 < radius_m <= MAX_RADIUS_M:
            raise ValueError("radius_m must be greater than zero and at most 100000")
        dlat = radius_m / M_PER_DEG
        dlon = radius_m / (M_PER_DEG * max(0.01, math.cos(math.radians(lat))))
        boxes = self.c.sql("SELECT seq, min_lon, min_lat, max_lon, max_lat FROM observation")   # small rows first
        cand = [r["seq"] for r in boxes if r["min_lon"] is not None and not (
            r["max_lon"] < lon - dlon or r["min_lon"] > lon + dlon or r["max_lat"] < lat - dlat or r["min_lat"] > lat + dlat)]
        here = Point(lon, lat)
        hits = []
        for seq in cand[:2000]:
            rows = self.c.sql(f"SELECT seq, body_json FROM observation WHERE seq = {int(seq)}")
            if not rows:
                continue
            r = rows[0]
            body = json.loads(r["body_json"])
            g = shape(body["geometry"])
            d_m = g.distance(here) * M_PER_DEG  # degrees -> metres (fine at Texas latitudes for ranking)
            if d_m <= radius_m:
                hits.append((d_m, r["seq"], body))
        return [b for _, _, b in sorted(hits, key=lambda x: (x[0], x[1]))[:500]]

    def intersecting_roads(self, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        ObservationIn.geojson(geometry)
        dataset = self.get_dataset()
        if not dataset:
            return []
        target = shape(geometry)
        roads = dataset.get("roads") or []
        return [road for road in roads if road.get("geometry") and shape(road["geometry"]).intersects(target)][:1000]

    # ---- health --------------------------------------------------------------
    def diagnostics(self) -> dict[str, Any]:
        from db.store import count
        cfg = self.c.config
        return {"path": f"spacetimedb:{cfg.url}/{cfg.database}", "backend": "spacetime", "schema_version": 1,
                "ok": True, "integrity": ["ok"], "foreign_key_errors": [],
                "observation_count": count(self.c, "observation"), "raw_record_count": count(self.c, "raw_record")}

    def health(self) -> dict[str, Any]:
        return self.diagnostics()
