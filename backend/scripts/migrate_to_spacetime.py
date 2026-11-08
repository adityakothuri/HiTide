"""Move everything the backend has into SpacetimeDB (idempotent: safe to re-run).

Sources -> SpacetimeDB tables:
  data/floodwatch.sqlite3   sources, observations (+ raw payloads, revision chains, original timestamps),
                            ingestion_runs, settings (dataset), inspection_tasks
  MongoDB (--mongo-uri)     the same evidence collections, if a team used the Mongo backend
  data/region_users.json    250 simulated Kerr County residents   -> app_user / user_contact / user_profile
  data/drivers.json         100 simulated Kerrville drivers (population "kerrville")
  data/user_registry.json   API-enrolled users (real phones -> private user_contact only)
  data/safety_state.json    live positions                        -> user_track
  data/outreach_log.jsonl   outreach audit log                    -> outreach_event

Run:  cd backend && uv run python -m scripts.migrate_to_spacetime [--dry-run] [--verify]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from db.spacetime import SpacetimeClient, SpacetimeConfig, SpacetimeError, opt
from db.store import SpacetimeDataStore
from db.evidence import _bbox
from evidence.store import prepare_observation, raw_hash

SQLITE = DATA_DIR / "floodwatch.sqlite3"
BATCH = 100


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


# ---- evidence ----------------------------------------------------------------------
def evidence_from_sqlite(path: Path) -> dict[str, list]:
    if not path.exists():
        return {"sources": [], "observations": [], "runs": [], "settings": [], "tasks": []}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {
        "sources": [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY id")],
        "observations": [json.loads(r[0]) for r in con.execute("SELECT body_json FROM observations ORDER BY rowid")],
        "runs": [dict(r) for r in con.execute("SELECT * FROM ingestion_runs ORDER BY id")],
        "settings": [(r[0], r[1]) for r in con.execute("SELECT key, body_json FROM settings")],
        "tasks": [json.loads(r[0]) for r in con.execute("SELECT body_json FROM inspection_tasks ORDER BY id")],
    }
    con.close()
    return out


def evidence_from_mongo(uri: str, database: str) -> dict[str, list]:
    from pymongo import MongoClient

    db = MongoClient(uri, serverSelectionTimeoutMS=3000)[database]
    strip = lambda d: {k: v for k, v in d.items() if k not in ("_id", "semantic_hash", "raw_record_id")}  # noqa: E731
    return {
        "sources": [{"id": s["_id"], **{k: v for k, v in s.items() if k != "_id"}} for s in db.sources.find()],
        "observations": [strip(o) for o in db.observations.find().sort("ingested_at", 1)],
        "runs": [strip(r) for r in db.ingestion_runs.find().sort("_id", 1)],
        "settings": [(s["_id"], json.dumps({k: v for k, v in s.items() if k != "_id"})) for s in db.settings.find()],
        "tasks": [strip(t) for t in db.inspection_tasks.find()],
    }


def migrate_evidence(c: SpacetimeClient, ev: dict[str, list], overwrite: bool = False) -> dict[str, int]:
    for s in ev["sources"]:
        c.call("upsert_source", s["id"], s["name"], s["category"], s["attribution"], int(s["expected_update_s"]))
    for body in ev["observations"]:
        _, semantic_hash = prepare_observation(body)     # same hash the live store computes
        raw_json, payload_hash = raw_hash(body.get("raw") or {})
        b = _bbox(body.get("geometry"))
        c.call("add_observation", semantic_hash, payload_hash, raw_json, json.dumps(body, allow_nan=False),
               opt(b[0]), opt(b[1]), opt(b[2]), opt(b[3]))   # duplicates are no-ops in the reducer
    existing_runs = {(r["source_id"], r["attempted_at"], r["status"]) for r in c.sql("SELECT * FROM ingestion_run")}
    for r in ev["runs"]:
        key = (r["source_id"], r.get("attempted_at") or r["fetched_at"], r["status"])
        if key not in existing_runs:
            c.call("record_ingestion", r["source_id"], r["status"], r.get("detail") or "", r.get("fetched_at") or "",
                   r.get("attempted_at") or r.get("fetched_at") or "")
    # Mutable state is copied only if absent (unless --overwrite): a re-run must not roll back newer edits.
    have_settings = {r["key"] for r in c.sql("SELECT key FROM setting")}
    have_tasks = {r["id"] for r in c.sql("SELECT id FROM inspection_task")}
    for key, body_json in ev["settings"]:
        if overwrite or key not in have_settings:
            c.call("set_setting", key, body_json)
    for t in ev["tasks"]:
        if overwrite or t["id"] not in have_tasks:
            c.call("save_task", t["id"], str(t.get("status", "")), str(t.get("road_id", "")), json.dumps(t, sort_keys=True))
    return {"sources": len(ev["sources"]), "observations": len(ev["observations"]), "ingestion_runs": len(ev["runs"]),
            "settings": len(ev["settings"]), "inspection_tasks": len(ev["tasks"])}


# ---- people, safety, outreach ---------------------------------------------------------------
def kerrville_drivers() -> list[dict[str, Any]]:
    drivers = _read_json(DATA_DIR / "drivers.json") or []
    if not drivers:
        return []
    from sim.town import load_town
    g = load_town().graph
    out = []
    for d in drivers:
        node = g.nodes.get(d["home_node"]) or g.nodes.get(int(d["home_node"]))
        if node is None:
            continue
        contact = d.get("emergency_contact") or {}
        parent = d.get("parent") or {}
        out.append({"id": d["id"], "name": d["name"], "age": d.get("age"), "phone": d["phone"],
                    "home": {"lat": float(node["y"]), "lon": float(node["x"])},
                    "contact_name": contact.get("name"), "contact_phone": contact.get("phone"),
                    "parent_phone": parent.get("phone") if isinstance(parent, dict) else None,
                    "profile": d.get("profile") or {}, "tags": list(d.get("tags") or []) + ["kerrville_driver"],
                    "simulated": True, "population": "kerrville"})
    return out


def people() -> dict[str, list[dict[str, Any]]]:
    region = [{**u, "simulated": True, "population": "region"} for u in (_read_json(DATA_DIR / "region_users.json") or [])]
    enrolled = [{**u, "simulated": False, "population": "enrolled"} for u in (_read_json(DATA_DIR / "user_registry.json") or [])]
    return {"region": region, "kerrville": kerrville_drivers(), "enrolled": enrolled}


def outreach_events() -> list[dict[str, Any]]:
    path = DATA_DIR / "outreach_log.jsonl"
    if not path.exists():
        return []
    events = []
    for n, line in enumerate(path.read_text().splitlines()):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        e.setdefault("id", f"legacy-{n}")
        events.append(e)
    return events


def safety_tracks() -> list[dict[str, Any]]:
    rows = _read_json(DATA_DIR / "safety_state.json") or {}
    return [{"user_id": uid, "motion": {**r["motion"], "mode": "live"}, "route": r.get("route", []), "pinged": True}
            for uid, r in rows.items()]


# ---- verify -----------------------------------------------------------------------------------
def counts(c: SpacetimeClient) -> dict[str, int]:
    tables = ("source", "observation", "raw_record", "ingestion_run", "setting", "inspection_task", "app_user",
              "user_contact", "user_profile", "user_track", "outreach_event")
    from db.store import count
    return {t: count(c, t) for t in tables}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="read the sources and print what would move")
    ap.add_argument("--verify", action="store_true", help="after migrating, compare source and SpacetimeDB counts")
    ap.add_argument("--sqlite", default=str(SQLITE))
    ap.add_argument("--overwrite", action="store_true", help="replace settings/tasks/positions already in SpacetimeDB")
    ap.add_argument("--mongo-uri", default=None)
    ap.add_argument("--mongo-db", default="floodwatch")
    args = ap.parse_args()

    ev = evidence_from_mongo(args.mongo_uri, args.mongo_db) if args.mongo_uri else evidence_from_sqlite(Path(args.sqlite))
    ppl = people()
    events = outreach_events()
    tracks = safety_tracks()
    plan = {"sources": len(ev["sources"]), "observations": len(ev["observations"]), "ingestion_runs": len(ev["runs"]),
            "settings": len(ev["settings"]), "inspection_tasks": len(ev["tasks"]),
            **{f"users_{k}": len(v) for k, v in ppl.items()}, "user_tracks": len(tracks), "outreach_events": len(events)}
    print("source data:", json.dumps(plan, indent=1))
    if args.dry_run:
        return 0

    c = SpacetimeClient(SpacetimeConfig.from_env(), timeout_s=60.0)
    if not c.database_exists():
        print(f"SpacetimeDB database '{c.config.database}' not reachable at {c.config.url}; run scripts/spacetime_up.sh",
              file=sys.stderr)
        return 2
    store = SpacetimeDataStore(c)
    try:
        migrate_evidence(c, ev, args.overwrite)
        for users in ppl.values():
            if users:
                store.seed_users(users)
        have_tracks = set(store.load_tracks())
        tracks = [t for t in tracks if args.overwrite or t["user_id"] not in have_tracks]
        if tracks:
            store.save_tracks(tracks)
        for i in range(0, len(events), 500):
            store.append_outreach(events[i:i + 500])
    except SpacetimeError as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    after = counts(c)
    print("SpacetimeDB now holds:", json.dumps(after, indent=1))
    if args.verify:
        n_users = sum(len(v) for v in ppl.values())
        n_obs_unique = len({prepare_observation(o)[1] for o in ev["observations"]})
        checks = [("observation", n_obs_unique), ("app_user", n_users), ("user_contact", n_users),
                  ("outreach_event", len({e["id"] for e in events})), ("inspection_task", len(ev["tasks"]))]
        ok = True
        print(f"\n{'table':<16}{'source':>9}{'spacetimedb':>13}  result")
        for table, want in checks:
            got = after[table]
            good = got >= want
            ok &= good
            print(f"{table:<16}{want:>9}{got:>13}  {'OK' if good else 'MISSING ROWS'}")
        c.close()
        return 0 if ok else 1
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
