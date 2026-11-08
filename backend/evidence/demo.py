"""Explicitly synthetic, deterministic evidence scenario located near Kerrville."""

from datetime import UTC, datetime, timedelta


def demo_dataset() -> dict:
    def road(id_, name, start, end, coordinates):
        return {"id": id_, "name": name, "from_node": start, "to_node": end,
                "physical_id": id_, "bidirectional": True,
                "geometry": {"type": "LineString", "coordinates": coordinates}}
    return {
        "id": "demo-kerrville-two-exits", "name": "Kerrville • synthetic two-exit exercise",
        "simulated": True,
        "description": "Synthetic neighborhood and crossings for a repeatable verification exercise; not real evacuation guidance.",
        "roads": [
            road("demo-west", "West crossing (synthetic)", "neighborhood", "safe-west", [[-99.145, 30.047], [-99.150, 30.049], [-99.157, 30.050]]),
            road("demo-east", "East crossing (synthetic)", "neighborhood", "safe-east", [[-99.145, 30.047], [-99.137, 30.045], [-99.130, 30.050]]),
            road("demo-north", "North crossing (synthetic)", "other", "safe-east", [[-99.127, 30.055], [-99.131, 30.053], [-99.130, 30.050]]),
            road("demo-south", "South route (synthetic)", "other", "safe-west", [[-99.127, 30.055], [-99.144, 30.058], [-99.157, 30.050]]),
        ],
        "communities": [{"id": "demo-community", "name": "Riverbank neighborhood (synthetic)", "node_id": "neighborhood", "households": 120},
                        {"id": "demo-other", "name": "North neighborhood (synthetic)", "node_id": "other", "households": 50}],
        "destinations": [{"id": "demo-safe-west", "name": "West destination (synthetic)", "node_id": "safe-west"},
                         {"id": "demo-safe-east", "name": "East destination (synthetic)", "node_id": "safe-east"}],
    }


def demo_observations(now: datetime | None = None, run_id: str = "initial") -> list[dict]:
    now = now or datetime.now(UTC)
    base = {"simulated": True, "geometry": None, "value": None, "unit": None, "valid_until": None}
    def obs(key, source, kind, road, access, age, quality, text):
        return {**base, "source_id": source, "source_record_id": f"{run_id}-{key}", "kind": kind,
                "road_id": road, "access": access, "quality": quality,
                "observed_at": (now - timedelta(minutes=age)).isoformat(),
                "raw": {"description": text, "demo_run_id": run_id}}
    result = [
        obs("west-closure", "demo_agency", "closure", "demo-west", "closed", 2, "agency", "Synthetic agency report: west crossing closed"),
        obs("east-old-report", "demo_local", "report", "demo-east", "open", 38, "operator", "Synthetic operator report: east crossing was clear 38 minutes ago"),
        obs("north-old-report", "demo_local", "report", "demo-north", "open", 38, "operator", "Synthetic stale report, alternative route remains available"),
        obs("south-open", "demo_agency", "closure", "demo-south", "open", 1, "agency", "Synthetic agency confirmation: south route open"),
        obs("gauge", "demo_usgs", "gauge", None, "unknown", 1, "sensor", "Synthetic nearby gauge trend; not road depth"),
        obs("warning", "demo_nws", "warning", None, "unknown", 1, "agency", "Synthetic active flood warning"),
    ]
    result[4].update(value=15.2, unit="ft")
    result[4]["raw"].update(trend="rising", parameter="gage_height")
    result[5]["geometry"] = {"type": "Polygon", "coordinates": [[[-99.17, 30.035], [-99.12, 30.035], [-99.12, 30.065], [-99.17, 30.065], [-99.17, 30.035]]]}
    return result
