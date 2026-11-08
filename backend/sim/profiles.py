"""Simulated flood-risk profiles for synthetic drivers. Design: docs/driver-profile.md.

Every State Farm field here is SIMULATED. Field names mirror what State Farm publicly documents
for Drive Safe & Save, policies, and claims; no real customer data is used. Profiles are for
protection only: nothing here may feed pricing, underwriting, or claims.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any, Iterable, Mapping

from sim.drivers import Driver

PROFILE_VERSION = 1
LOW_LYING_PERCENTILE = 0.02  # lowest 2% of segment elevations count as low-lying crossings
NIGHT_SHARE_NIGHT_TRIP = 0.45
MAX_CROSSINGS = 3

# Approximate water depth (inches) at which each vehicle class may stall or float. Not a safety rating.
STALL_DEPTH_IN = {"compact": 12, "sedan": 12, "ev": 12, "minivan": 15, "suv": 18, "truck": 24}

SOURCES = {
    "dss": "sf_dss", "steer_clear": "sf_steer_clear", "derived": "derived", "policy": "sf_policy",
    "claims": "sf_claims", "adt": "sf_adt", "needs": "self_reported", "consent": "self_reported",
    "demo_signals": "sf_live",
}

# Demo personas: explicit needs and signals so each profile factor visibly changes the response.
PERSONAS: dict[str, dict[str, Any]] = {
    "demo-d": {"needs": ["mobility_assist"], "language": "en", "night_driving_share": 0.6,
               "past_flood_claims": [{"year": 2025, "type": "vehicle_flood_total"}]},
    "demo-t": {"steer_clear": True, "language": "en"},
    "d-005": {"needs": ["wheelchair_user"], "preferred_channel": "voice"},
    "d-010": {"language": "es"},
    "d-020": {"other_policies": ["homeowners"], "adt_water_sensors": 5,
              "demo_signals": [{"kind": "adt_water_sensor", "at_min": 30}]},
    "d-030": {"demo_signals": [{"kind": "roadside_request", "at_min": 38}]},
    "d-040": {"needs": ["hearing_loss"], "preferred_channel": "sms"},
    "d-050": {"needs": ["powered_medical_equipment"], "household": {"dependents_at_home": 1}},
    "d-060": {"new_to_area": True, "language": "es"},
}


def age_band(age: int) -> str:
    if age <= 19:
        return "teen"
    if age >= 70:
        return "70+"
    if age >= 65:
        return "65-69"
    return "20-64"


def low_lying_edges(segments: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Edge id -> road name for the lowest-elevation segments (our stand-in for low-water crossings)."""
    rows = [s for s in segments if s.get("elev_m") is not None]
    if not rows:
        return {}
    cutoff = sorted(s["elev_m"] for s in rows)[int(len(rows) * LOW_LYING_PERCENTILE)]
    return {s["edge_id"]: (s.get("name") or "unnamed road") for s in rows if s["elev_m"] <= cutoff}


def _frequent_crossings(driver: Driver, trips_per_week: Mapping[str, int], low: Mapping[str, str]) -> list[dict]:
    totals: dict[str, int] = {}
    for route in driver.routes:
        names = {low[e] for e in route.edge_ids if e in low}
        for name in names:
            totals[name] = totals.get(name, 0) + trips_per_week[route.label]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:MAX_CROSSINGS]
    return [{"road": n, "trips_per_week": t} for n, t in ranked]


def _dss(rng: random.Random, miles_30d: float, steer_clear: bool) -> dict:
    per100 = lambda lo, hi: round(rng.uniform(lo, hi) * miles_30d / 100)  # noqa: E731
    return {
        "enrolled": True,
        "beacon_id": f"BCN-{rng.randint(100000, 999999)}",
        "score_14d": rng.randint(62, 100),
        "miles_30d": round(miles_30d, 1),
        "annual_mileage": round(miles_30d * 12.2),
        "events_30d": {"speeding": per100(0, 3), "hard_braking": per100(0, 2), "fast_acceleration": per100(0, 2),
                       "sharp_cornering": per100(0, 1.5), "phone_distraction": per100(0, 2.5)},
        "accident_assistance_enabled": rng.random() < 0.6,
        "app_health": {"last_daily_signal_days_ago": rng.choice([0, 0, 0, 0, 1, 3]), "location_always": rng.random() < 0.9},
        "steer_clear_enrolled": steer_clear,
    }


def build_profile(driver: Driver, low: Mapping[str, str]) -> dict:
    rng = random.Random(f"profile-{driver.id}")
    p = PERSONAS.get(driver.id, {})
    trips_per_week = {r.label: rng.randint(2, 10) for r in driver.routes}
    miles_30d = sum(r.length_m / 1609.34 * 2 * trips_per_week[r.label] * 30 / 7 for r in driver.routes)
    steer_clear = p.get("steer_clear", driver.is_teen and rng.random() < 0.5)
    dss = _dss(rng, miles_30d, steer_clear)
    ev = dss["events_30d"]
    night_default = NIGHT_SHARE_NIGHT_TRIP if "night_trip" in driver.tags else round(rng.uniform(0.02, 0.3), 2)
    other = p.get("other_policies", rng.choice([[], ["homeowners"], ["renters"]]))
    return {
        "version": PROFILE_VERSION,
        "simulated": True,
        "sources": SOURCES,
        "consent": {"flood_alerts": True, "share_location_on_escalation": True, "drone_check": rng.random() < 0.8},
        "dss": dss,
        "derived": {
            "trips_per_week": trips_per_week,
            "frequent_crossings": _frequent_crossings(driver, trips_per_week, low),
            "night_driving_share": p.get("night_driving_share", night_default),
            "speeding_per_100mi": round(ev["speeding"] / max(miles_30d, 1) * 100, 1),
            "distraction_per_100mi": round(ev["phone_distraction"] / max(miles_30d, 1) * 100, 1),
        },
        "policy": {
            "age_band": age_band(driver.age),
            "years_licensed": max(0, driver.age - 16 - rng.randint(0, 3)),
            "vehicle_year": rng.randint(2008, 2025),
            "stall_depth_in": STALL_DEPTH_IN.get(driver.vehicle.type, 12),
            "preferred_channel": p.get("preferred_channel", rng.choice(["sms", "sms", "voice", "app"])),
            "language": p.get("language", "es" if rng.random() < 0.15 else "en"),
            "other_policies": other,
            "home_type": "manufactured" if other and rng.random() < 0.1 else ("house" if other else "unknown"),
            "has_flood_coverage": bool(other) and rng.random() < 0.2,
            "agent_id": f"agent-ker-{rng.randint(1, 6):02d}",
        },
        "claims": {"past_flood_claims": p.get("past_flood_claims", [])},
        "adt": {"enrolled": "adt_water_sensors" in p, "water_sensors": p.get("adt_water_sensors", 0)},
        "needs": p.get("needs", []),
        "household": {"new_to_area": p.get("new_to_area", rng.random() < 0.08),
                      "pets": rng.random() < 0.4, "kids_often_aboard": rng.random() < 0.25,
                      **p.get("household", {})},
        "demo_signals": p.get("demo_signals", []),
    }


def attach_profiles(drivers: Iterable[Driver], segments: Iterable[Mapping[str, Any]]) -> list[Driver]:
    low = low_lying_edges(segments)
    return [replace(d, profile=build_profile(d, low)) for d in drivers]
