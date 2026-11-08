"""Explainable road evidence and directed connectivity; never equate missing with open."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from shapely.geometry import shape

DIRECT_KINDS = {"closure", "report", "drone"}
FRESH_SECONDS = {"closure": 1800, "report": 900, "drone": 600}


def instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def is_current(observation: dict, now: datetime) -> bool:
    observed = instant(observation.get("observed_at"))
    expiry = instant(observation.get("valid_until"))
    if observed is None or observed > now or (expiry and expiry <= now):
        return False
    if expiry:
        return True
    return (now - observed).total_seconds() <= FRESH_SECONDS.get(observation["kind"], 900)


def latest_evidence(observations: list[dict]) -> list[dict]:
    """Collapse record revisions, then retain each source's latest direct road report."""
    superseded = {o.get("supersedes_id") for o in observations if o.get("supersedes_id")}
    revisions: dict[tuple, dict] = {}
    for o in observations:
        if o["id"] in superseded:
            continue
        key = (o["source_id"], o.get("source_record_id") or o["id"])
        old = revisions.get(key)
        if old is None or (instant(o.get("ingested_at")) or datetime.min.replace(tzinfo=UTC)) > (instant(old.get("ingested_at")) or datetime.min.replace(tzinfo=UTC)):
            revisions[key] = o
    by_source: dict[tuple, dict] = {}
    for o in revisions.values():
        key = (o["source_id"], o.get("road_id"), o["kind"]) if o["kind"] in DIRECT_KINDS else (o["source_id"], o.get("source_record_id") or o["id"], o["kind"])
        old = by_source.get(key)
        # Delayed ingestion of an older measurement cannot replace a newer measurement.
        minimum = datetime.min.replace(tzinfo=UTC)
        if old is None or ((instant(o.get("observed_at")) or minimum), (instant(o.get("ingested_at")) or minimum)) > ((instant(old.get("observed_at")) or minimum), (instant(old.get("ingested_at")) or minimum)):
            by_source[key] = o
    return list(by_source.values())


def assess_roads(dataset: dict, observations: list[dict], now: datetime) -> list[dict]:
    roads = dataset.get("roads", [])
    physical = {r["id"]: r.get("physical_id", r["id"]) for r in roads}
    grouped: dict[str, list[dict]] = defaultdict(list)
    # Keep individual gauge/warning records out of direct passability assessment.
    latest = latest_evidence([{**o, "road_id": physical.get(o.get("road_id"), o.get("road_id"))} for o in observations])
    warning_shapes = []
    for o in latest:
        if o["kind"] == "warning" and o.get("geometry") and is_current(o, now):
            try:
                warning_shapes.append((o, shape(o["geometry"])))
            except (TypeError, ValueError):
                continue
    for o in latest:
        if o.get("road_id") and o["kind"] in DIRECT_KINDS:
            grouped[physical.get(o["road_id"], o["road_id"])].append(o)
    result = []
    for road in roads:
        evidence = grouped.get(physical[road["id"]], [])
        contexts = []
        if road.get("geometry"):
            geometry = shape(road["geometry"])
            contexts = [o for o, polygon in warning_shapes if polygon.intersects(geometry)]
        current = [o for o in evidence if is_current(o, now)]
        statuses = {o.get("access", "unknown") for o in current} - {"unknown"}
        # An unexpired agency closure cannot be silently reopened by imagery or a report.
        agency_closures = [o for o in evidence if o.get("quality") == "agency" and o.get("access") == "closed" and (not o.get("valid_until") or (instant(o["valid_until"]) or now) > now)]
        conflict = len(statuses) > 1 or bool(agency_closures and "open" in statuses)
        trusted_open = any(o.get("access") == "open" and o.get("quality") in {"agency", "operator", "sensor"} for o in current)
        if agency_closures or "closed" in statuses:
            access = "closed"
        elif conflict:
            access = "unknown"
        elif "restricted" in statuses:
            access = "restricted"
        elif trusted_open:
            access = "open"
        else:
            access = "unknown"
        freshness = "current" if current else ("stale" if evidence else "missing")
        reasons = []
        if freshness == "missing":
            reasons.append("No direct road observation is available")
        elif freshness == "stale":
            reasons.append("Direct road evidence is stale or expired")
        if conflict:
            reasons.append("Sources disagree about road access")
        if agency_closures:
            reasons.append("Agency closure remains in effect until superseded or expired")
        if statuses == {"open"} and not trusted_open:
            reasons.append("Open report is unverified; passability remains unknown")
        if any(o.get("raw", {}).get("outcome") == "inconclusive" for o in current):
            reasons.append("Latest inspection was inconclusive")
        if contexts:
            reasons.append("Road intersects a current warning area; this is hazard context, not a closure")
        result.append({**road, "physical_id": physical[road["id"]], "access": access,
                       "freshness": freshness, "agreement": "conflicting" if conflict else "consistent",
                       "evidence_ids": [o["id"] for o in evidence] + [o["id"] for o in contexts],
                       "context_ids": [o["id"] for o in contexts], "reasons": reasons})
    return result


def reachable(roads: list[dict], origin: str, destinations: set[str], *, conservative: bool, blocked: str | None = None, exclude_node: str | None = None) -> bool:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for road in roads:
        if road.get("physical_id", road["id"]) == blocked or road["access"] == "closed":
            continue
        if conservative and (road["access"] != "open" or road["agreement"] == "conflicting"):
            continue
        src, dst = str(road["from_node"]), str(road["to_node"])
        if exclude_node in {src, dst}:
            continue
        adjacency[src].append(dst)
        if road.get("bidirectional"):
            adjacency[dst].append(src)
    queue = deque([str(origin)])
    seen = set(queue)
    while queue:
        node = queue.popleft()
        if node in destinations:
            return True
        for neighbour in adjacency[node]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return False


def analyze(dataset: dict, observations: list[dict], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    roads = assess_roads(dataset, observations, now)
    destinations = {str(d["node_id"]) for d in dataset.get("destinations", [])}
    communities = []
    for community in dataset.get("communities", []):
        origin = str(community["node_id"])
        possible = reachable(roads, origin, destinations, conservative=False)
        confirmed = reachable(roads, origin, destinations, conservative=True)
        exit_ids = set()
        for road in roads:
            if road["access"] == "closed":
                continue
            neighbour = None
            if str(road["from_node"]) == origin:
                neighbour = str(road["to_node"])
            elif road.get("bidirectional") and str(road["to_node"]) == origin:
                neighbour = str(road["from_node"])
            if neighbour is not None and reachable(roads, neighbour, destinations, conservative=False, exclude_node=origin):
                exit_ids.add(road["physical_id"])
        communities.append({**community, "optimistic_access": possible, "conservative_access": confirmed,
                            "remaining_exits": len(exit_ids), "access_label": "Confirmed modeled access" if confirmed else ("Access depends on uncertain roads" if possible else "No modeled exit")})
    candidates = []
    seen_physical = set()
    for road in roads:
        if not communities or not destinations:
            break  # Unknown roads alone cannot establish inspection value.
        physical = road["physical_id"]
        if physical in seen_physical:
            continue
        seen_physical.add(physical)
        gap = road["access"] in {"unknown", "restricted"} or road["agreement"] == "conflicting" or road["freshness"] == "stale"
        if not gap:
            continue
        affected = [c for c in communities if c["optimistic_access"] and not reachable(roads, str(c["node_id"]), destinations, conservative=False, blocked=physical)]
        if not affected:
            continue
        households = sum(c.get("households", 0) or 0 for c in affected)
        score = 1000 * len(affected) + min(households, 500) + (80 if road["agreement"] == "conflicting" else 0) + (40 if road["freshness"] == "missing" else 30 if road["freshness"] == "stale" else 10) + (20 if road["context_ids"] else 0)
        reasons = list(road["reasons"])
        if affected:
            reasons.insert(0, f"Loss of this crossing removes all modeled exits for {len(affected)} neighborhood(s)")
        coords = road.get("geometry", {}).get("coordinates", [])
        location = {"type": "Point", "coordinates": coords[len(coords) // 2]} if coords else None
        candidates.append({"road_id": road["id"], "physical_id": physical, "road_name": road["name"],
                           "priority": score, "reasons": reasons, "affected_communities": [c["id"] for c in affected],
                           "location": location, "evidence_ids": sorted(road["evidence_ids"])})
    candidates.sort(key=lambda c: (-c["priority"], c["road_id"]))
    return {"roads": roads, "communities": communities, "candidates": candidates}
