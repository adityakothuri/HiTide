"""MongoDB evidence persistence with real geospatial indexes and transactions.

Use a replica set (including a local single-node replica set) for atomic mission
writes. No fallback to non-transactional writes is performed. Raw images belong
in file/object storage; observations contain their metadata and references.
"""

from __future__ import annotations

import hashlib
import math
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, MongoClient
from pymongo.client_session import ClientSession

from evidence.models import ObservationIn, now_iso
from evidence.store import SOURCES, encoded


class MongoStore:
    def __init__(self, uri: str, database: str = "floodwatch"):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        self.db = self.client[database]
        self._lock = threading.RLock()
        self._session: ClientSession | None = None
        self.client.admin.command("ping")
        hello = self.client.admin.command("hello")
        if not hello.get("setName") and hello.get("msg") != "isdbgrid":
            self.client.close()
            raise RuntimeError("MongoDB requires a replica set for atomic mission transactions")
        self._migrate()

    def _migrate(self) -> None:
        version = self.db.settings.find_one({"_id": "schema"})
        if version and version.get("version", 0) > 1:
            raise RuntimeError("MongoDB schema is newer than this application supports")
        self.db.observations.create_index("semantic_hash", unique=True)
        self.db.observations.create_index([("source_id", ASCENDING), ("source_record_id", ASCENDING), ("revision", DESCENDING)], unique=True)
        self.db.observations.create_index([("geometry", GEOSPHERE)])
        self.db.observations.create_index("supersedes_id")
        self.db.observations.create_index("ingested_at")
        self.db.raw_records.create_index([("source_id", ASCENDING), ("payload_hash", ASCENDING)], unique=True)
        self.db.ingestion_runs.create_index([("source_id", ASCENDING), ("_id", DESCENDING)])
        self.db.roads.create_index([("geometry", GEOSPHERE)])
        self.db.roads.create_index([("dataset_id", ASCENDING), ("id", ASCENDING)], unique=True)
        self.db.inspection_tasks.create_index("road_id")
        self.db.inspection_tasks.create_index("status")
        for source_id, name, category, attribution, update_s in SOURCES:
            self.db.sources.update_one({"_id": source_id}, {"$setOnInsert": {
                "id": source_id, "name": name, "category": category,
                "attribution": attribution, "expected_update_s": update_s}}, upsert=True)
        self.db.settings.update_one({"_id": "schema"}, {"$setOnInsert": {"version": 1}}, upsert=True)

    def close(self) -> None:
        with self._lock:
            self.client.close()

    @contextmanager
    def transaction(self) -> Iterator[MongoStore]:
        """Compose writes in one replica-set transaction, holding no network fetches."""
        with self._lock:
            if self._session is not None:
                yield self
                return
            with self.client.start_session() as session:
                self._session = session
                try:
                    with session.start_transaction():
                        yield self
                finally:
                    self._session = None

    def _ensure_source(self, source_id: str) -> None:
        self.db.sources.update_one({"_id": source_id}, {"$setOnInsert": {
            "id": source_id, "name": source_id.replace("_", " "), "category": "report",
            "attribution": "Submitted evidence", "expected_update_s": 300}},
            upsert=True, session=self._session)

    @staticmethod
    def _observation_body(document: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in document.items()
                if key not in {"_id", "semantic_hash", "raw_record_id", "revision"}}

    def add_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        body = ObservationIn.model_validate(observation).model_dump()
        semantic = {key: value for key, value in body.items()
                    if key not in {"id", "ingested_at", "supersedes_id", "source_mode"}}
        semantic["raw"] = {key: value for key, value in body["raw"].items()
                           if key not in {"fetched_at", "ingested_at", "retrieved_at", "source_mode"}}
        semantic_hash = hashlib.sha256(encoded(semantic).encode()).hexdigest()
        with self.transaction():
            prior = self.db.observations.find_one({"semantic_hash": semantic_hash}, session=self._session)
            if prior:
                return self._observation_body(prior)
            latest = self.db.observations.find_one(
                {"source_id": body["source_id"], "source_record_id": body["source_record_id"]},
                sort=[("revision", DESCENDING)], session=self._session)
            if body["supersedes_id"] and (latest is None or body["supersedes_id"] != latest["id"]):
                raise ValueError("supersedes_id must identify the latest revision of the same source record")
            self._ensure_source(body["source_id"])
            body["id"] = body["id"] or f"obs-{uuid.uuid4().hex}"
            body["ingested_at"] = now_iso()
            body["supersedes_id"] = body["supersedes_id"] or (latest["id"] if latest else None)
            raw_hash = hashlib.sha256(encoded(body["raw"]).encode()).hexdigest()
            raw_id = hashlib.sha256(f"{body['source_id']}:{raw_hash}".encode()).hexdigest()
            self.db.raw_records.update_one({"_id": raw_id}, {"$setOnInsert": {
                "source_id": body["source_id"], "payload_hash": raw_hash,
                "payload": body["raw"], "received_at": body["ingested_at"]}},
                upsert=True, session=self._session)
            self.db.observations.insert_one({"_id": body["id"], **body, "semantic_hash": semantic_hash,
                "raw_record_id": raw_id, "revision": latest["revision"] + 1 if latest else 1}, session=self._session)
        return body

    def list_observations(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._observation_body(doc) for doc in self.db.observations.find({}, session=self._session)
                    .sort([("ingested_at", ASCENDING), ("revision", ASCENDING)])]

    def list_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []
            for source in self.db.sources.find({}, {"_id": 0}, session=self._session).sort("id", ASCENDING):
                last = self.db.ingestion_runs.find_one({"source_id": source["id"]}, sort=[("_id", DESCENDING)], session=self._session) or {}
                success = self.db.ingestion_runs.find_one({"source_id": source["id"], "status": "live"},
                    sort=[("_id", DESCENDING)], session=self._session) or {}
                result.append({**source, "status": last.get("status", "not_fetched"),
                    "detail": last.get("detail"), "fetched_at": last.get("fetched_at"),
                    "last_attempt_at": last.get("attempted_at"), "last_successful_fetch_at": success.get("fetched_at")})
            return result

    def record_ingestion(self, source_id: str, status: str, detail: str = "", fetched_at: str | None = None) -> None:
        with self.transaction():
            self._ensure_source(source_id)
            self.db.ingestion_runs.insert_one({"source_id": source_id, "status": status, "detail": detail,
                "fetched_at": fetched_at or (now_iso() if status == "live" else None),
                "attempted_at": now_iso()}, session=self._session)

    def get_dataset(self) -> dict[str, Any] | None:
        with self._lock:
            document = self.db.settings.find_one({"_id": "dataset"}, session=self._session)
            if document is None:
                return None
            body = document["body"]
            roads = self.db.roads.find({"dataset_id": document["dataset_id"]}, session=self._session).sort("ordinal", ASCENDING)
            return {**body, "roads": [{k: v for k, v in road.items() if k not in {"_id", "dataset_id", "ordinal"}} for road in roads]}

    def set_dataset(self, dataset: dict[str, Any]) -> None:
        dataset_id = str(dataset.get("id") or "active")
        roads = dataset.get("roads", [])
        with self.transaction():
            self.db.settings.replace_one({"_id": "dataset"}, {"_id": "dataset", "dataset_id": dataset_id,
                "body": {k: v for k, v in dataset.items() if k != "roads"}}, upsert=True, session=self._session)
            self.db.roads.delete_many({"dataset_id": dataset_id}, session=self._session)
            if roads:
                self.db.roads.insert_many([{"_id": f"{dataset_id}:{road['id']}", "dataset_id": dataset_id,
                    "ordinal": index, **road} for index, road in enumerate(roads)], session=self._session)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.db.inspection_tasks.find({}, {"_id": 0}, session=self._session).sort("id", ASCENDING))

    def save_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if not task.get("id"):
            raise ValueError("inspection task requires an id")
        with self.transaction():
            self.db.inspection_tasks.replace_one({"_id": task["id"]}, {"_id": task["id"], **task},
                upsert=True, session=self._session)
        return task

    def nearby_observations(self, lon: float, lat: float, radius_m: float) -> list[dict[str, Any]]:
        """Return stored evidence near a point, using MongoDB's spherical index."""
        ObservationIn.geojson({"type": "Point", "coordinates": [lon, lat]})
        if not math.isfinite(radius_m) or not 0 < radius_m <= 100_000:
            raise ValueError("radius_m must be greater than zero and at most 100000")
        with self._lock:
            query = {"geometry": {"$near": {"$geometry": {"type": "Point", "coordinates": [lon, lat]}, "$maxDistance": radius_m}}}
            return [self._observation_body(doc) for doc in self.db.observations.find(query, session=self._session).limit(500)]

    def intersecting_roads(self, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        """Find active-dataset roads intersecting GeoJSON with a 2dsphere index."""
        ObservationIn.geojson(geometry)
        with self._lock:
            dataset = self.db.settings.find_one({"_id": "dataset"}, session=self._session)
            if dataset is None:
                return []
            query = {"dataset_id": dataset["dataset_id"], "geometry": {"$geoIntersects": {"$geometry": geometry}}}
            return [{k: v for k, v in road.items() if k not in {"_id", "dataset_id", "ordinal"}}
                    for road in self.db.roads.find(query, session=self._session).limit(1000)]

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            ping = self.client.admin.command("ping")
            source_errors = list(self.db.observations.aggregate([
                {"$lookup": {"from": "sources", "localField": "source_id", "foreignField": "_id", "as": "matched"}},
                {"$match": {"matched": {"$size": 0}}}, {"$project": {"_id": 0, "id": 1, "source_id": 1}}, {"$limit": 20}]))
            geo_indexes = [name for name, spec in self.db.observations.index_information().items()
                           if ("geometry", "2dsphere") in spec["key"]]
            healthy = bool(ping.get("ok")) and not source_errors and bool(geo_indexes)
            return {"path": f"mongodb:{self.db.name}", "backend": "mongodb", "schema_version": 1,
                    "ok": healthy, "integrity": ["ok"] if healthy else ["integrity checks failed"],
                    "foreign_key_errors": source_errors, "geospatial_indexes": geo_indexes,
                    "observation_count": self.db.observations.count_documents({}),
                    "raw_record_count": self.db.raw_records.count_documents({})}

    def health(self) -> dict[str, Any]:
        return self.diagnostics()
