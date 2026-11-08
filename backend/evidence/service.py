"""Persistent evidence-to-inspection workflow shared by REST and live refresh."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from typing import Any

from evidence.analysis import analyze
from evidence.demo import demo_dataset, demo_observations
from evidence.models import now_iso
from evidence.store import Store


def town_dataset(town: Any) -> dict:
    roads = []
    if town is not None:
        for feature in town.segments_fc["features"]:
            props = feature["properties"]
            road_id = props["edge_id"]
            u, v, key = road_id.split("-")
            physical = "-".join([*sorted([u, v]), key])
            roads.append({"id": road_id, "physical_id": physical, "name": props.get("name") or "Unnamed road", "from_node": u, "to_node": v, "geometry": feature["geometry"]})
    return {"id": "kerrville", "name": "Kerrville road evidence", "simulated": False,
            "description": "Cached OSM road network. Configure neighborhood origins and destinations before evacuation-impact analysis.",
            "roads": roads, "communities": [], "destinations": []}


class EvidenceService:
    def __init__(self, store: Store, town: Any = None):
        self.store = store
        self._lock = threading.RLock()
        if store.get_dataset() is None:
            store.set_dataset(town_dataset(town))

    def _scope(self, observations: list[dict], dataset: dict) -> list[dict]:
        run_id = dataset.get("run_id")
        if not run_id:
            return [o for o in observations if not o.get("raw", {}).get("demo_run_id")]
        return [o for o in observations if not o.get("raw", {}).get("demo_run_id") or o["raw"]["demo_run_id"] == run_id]

    def snapshot(self) -> dict:
        with self._lock:
            dataset = self.store.get_dataset() or town_dataset(None)
            all_observations = self.store.list_observations()
            observations = self._scope(all_observations, dataset)
            evaluated = analyze(dataset, observations)
            tasks = self._sync_tasks(dataset, evaluated["candidates"])
            metadata = {k: v for k, v in dataset.items() if k != "roads"}
            return {"observations": observations, "roads": evaluated["roads"], "tasks": tasks,
                    "communities": evaluated["communities"], "sources": self.store.list_sources(),
                    "dataset": metadata, "generated_at": now_iso(), "historical_observation_count": len(all_observations),
                    "limitations": (["Configure neighborhood origins and evacuation destinations to rank inspections."] if not dataset.get("communities") or not dataset.get("destinations") else []) + ["Modeled connectivity is not a declaration that a route is safe.", "Single-crossing sensitivity analysis; joint failures are not yet evaluated."]}

    def _sync_tasks(self, dataset: dict, candidates: list[dict]) -> list[dict]:
        existing = {t["id"]: t for t in self.store.list_tasks()}
        active_ids = set()
        run = dataset.get("run_id", "")
        for candidate in candidates:
            identifier = hashlib.sha256(f"{dataset['id']}:{run}:{candidate['physical_id']}".encode()).hexdigest()[:20]
            tid = f"inspection-{identifier}"
            active_ids.add(tid)
            fingerprint = hashlib.sha256(json.dumps({"evidence": candidate["evidence_ids"], "reasons": candidate["reasons"], "affected": candidate["affected_communities"]}, sort_keys=True).encode()).hexdigest()
            previous = existing.get(tid)
            task = {**candidate, "id": tid, "dataset_id": dataset["id"], "run_id": run,
                    "status": "queued", "created_at": now_iso(), "fingerprint": fingerprint}
            if previous:
                task = {**previous, **candidate}
                if previous.get("fingerprint") != fingerprint and previous["status"] == "completed":
                    task.update(status="queued", reopened_at=now_iso())
                task["fingerprint"] = fingerprint
            if task != previous:
                self.store.save_task(task)
            existing[tid] = task
        # Obsolete queued tasks are retained in history, but cannot be assigned.
        for tid, task in existing.items():
            if task.get("dataset_id") != dataset["id"] or task.get("run_id", "") != run:
                continue
            if tid not in active_ids and task["status"] in {"queued", "assigned", "inconclusive"}:
                task = {**task, "status": "completed", "completed_at": now_iso(), "resolution": "Evidence changed; inspection no longer resolves an active consequential gap"}
                self.store.save_task(task)
                existing[tid] = task
        return sorted([t for t in existing.values() if t.get("dataset_id") == dataset["id"] and t.get("run_id", "") == run], key=lambda t: (t["status"] == "completed", -t["priority"], t["id"]))

    def add_report(self, observation: dict) -> dict:
        with self._lock:
            dataset = self.store.get_dataset() or {}
            if observation.get("road_id") and observation["road_id"] not in {r["id"] for r in dataset.get("roads", [])}:
                raise ValueError("Road does not belong to the active dataset")
            observation = {**observation, "source_id": "local_reports", "kind": "report", "quality": "unverified", "source_mode": "manual"}
            observation["source_record_id"] = observation.get("source_record_id") or f"report-{uuid.uuid4().hex}"
            observation["raw"] = {**observation.get("raw", {})}
            if dataset.get("run_id"):
                observation["simulated"] = True
                observation["raw"]["demo_run_id"] = dataset["run_id"]
            self.store.add_observation(observation)
            self.store.record_ingestion("local_reports", "manual", "Operator-submitted unverified report")
            return self.snapshot()

    async def ingest(self) -> dict:
        from evidence.ingestion import ingest_feeds
        result = await ingest_feeds(self.store)
        return {"ingestion": result, "state": await asyncio.to_thread(self.snapshot)}

    def start_demo(self) -> dict:
        with self._lock, self.store.transaction():
            run_id = uuid.uuid4().hex
            dataset = {**demo_dataset(), "run_id": run_id}
            self.store.set_dataset(dataset)
            for observation in demo_observations(run_id=run_id):
                observation["source_mode"] = "simulated"
                self.store.add_observation(observation)
            for source in ("demo_agency", "demo_local", "demo_usgs", "demo_nws"):
                self.store.record_ingestion(source, "simulated", "Synthetic two-exit scenario")
            return self.snapshot()

    def use_town(self, town: Any) -> dict:
        with self._lock:
            self.store.set_dataset(town_dataset(town))
            return self.snapshot()

    def configure(self, communities: list[dict], destinations: list[dict]) -> dict:
        with self._lock:
            dataset = self.store.get_dataset() or {}
            nodes = {str(r[key]) for r in dataset.get("roads", []) for key in ("from_node", "to_node")}
            for item in [*communities, *destinations]:
                if str(item["node_id"]) not in nodes:
                    raise ValueError(f"Unknown road graph node: {item['node_id']}")
            for group in (communities, destinations):
                if len({item["id"] for item in group}) != len(group):
                    raise ValueError("Configuration identifiers must be unique within each group")
            self.store.set_dataset({**dataset, "communities": communities, "destinations": destinations})
            return self.snapshot()

    def _task(self, task_id: str) -> dict:
        task = next((t for t in self.snapshot()["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise KeyError("Inspection task not found in active dataset")
        return task

    def assign(self, task_id: str) -> dict:
        with self._lock:
            task = self._task(task_id)
            if task["status"] not in {"queued", "inconclusive"}:
                raise ValueError("Only queued or inconclusive inspections can be assigned")
            self.store.save_task({**task, "status": "assigned", "assigned_at": now_iso()})
            return self.snapshot()

    def complete(self, task_id: str, result: dict) -> dict:
        with self._lock, self.store.transaction():
            task = self._task(task_id)
            if task["status"] != "assigned":
                raise ValueError("Assign the inspection before submitting a result")
            dataset = self.store.get_dataset() or {}
            raw = {**result, "task_id": task_id}
            if dataset.get("run_id"):
                raw["demo_run_id"] = dataset["run_id"]
            observation = {"source_id": "drone", "source_record_id": f"{task_id}:{uuid.uuid4().hex}",
                           "kind": "drone", "observed_at": result["observed_at"], "road_id": task["road_id"],
                           "geometry": task.get("location"), "access": result["outcome"] if result["outcome"] != "inconclusive" else "unknown",
                           "quality": "operator", "source_mode": "simulated" if dataset.get("simulated") else "manual",
                           "simulated": bool(dataset.get("simulated")), "raw": raw,
                           "value": result.get("water_depth_in"), "unit": "in" if result.get("water_depth_in") is not None else None}
            persisted = self.store.add_observation(observation)
            self.store.record_ingestion("drone", observation["source_mode"], "Operator-reviewed inspection result")
            status = "inconclusive" if result["outcome"] == "inconclusive" else "completed"
            self.store.save_task({**task, "status": status, "completed_at": now_iso(), "result_observation_id": persisted["id"], "outcome": result["outcome"]})
            return self.snapshot()
