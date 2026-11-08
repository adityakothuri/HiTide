"""Generate simulated opted-in Kerr County residents for the per-user danger pipeline -> data/region_users.json.

Homes are drawn from the region's populated areas (data/region/hill_country/nodes.json), weighted by households,
jittered ~200 m. Profiles reuse sim/profiles.build_profile; "frequent crossings" are the real critical points
(low-water crossings, bridges) within 3 km of home. Phones: "sim:<id>" (never sendable) except the demo personas,
which use env:DEMO_PHONE_* refs (allowlisted teammates; hc-dana -> DEMO_PHONE_DANA, the live phone-app demo). Deterministic (seeded).

Run: cd backend && uv run python scripts/gen_region_users.py [--n 250]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from typing import Any

from app.config import DATA_DIR
from safety.users import REGION_USERS_PATH, atomic_write_json
from sim.drivers import FIRST, LAST, VEHICLES, Contact, Driver, Vehicle
from sim.profiles import build_profile

SEED = 20250704
JITTER_M = 200.0
CROSSING_RADIUS_M = 3000.0
M_PER_DEG = 111_000.0

# Demo personas, placed where the July 4, 2025 water was (see vault/Experiments). Phones are env refs only.
PERSONAS: list[dict[str, Any]] = [
    {"id": "hc-ruth", "name": "Ruth Alvarez", "age": 78, "vehicle": ("Toyota", "Camry", "sedan"),
     "home": (30.0688, -99.3345), "phone": "env:DEMO_PHONE_B", "contact_name": "Teammate C",
     "contact_phone": "env:DEMO_PHONE_C", "needs": ["mobility_assist"], "tags": ["demo", "low_ground"]},
    {"id": "hc-marco", "name": "Marco Reyes", "age": 34, "vehicle": ("Ford", "F-150", "truck"),
     "home": (30.0560, -99.1570), "phone": "env:DEMO_PHONE_A", "contact_name": "Ana Reyes",
     "contact_phone": "sim:hc-marco-contact", "needs": [], "tags": ["demo", "commuter"]},
    {"id": "hc-jess", "name": "Jess Carter", "age": 17, "vehicle": ("Honda", "Civic", "compact"),
     "home": (30.0745, -99.2410), "phone": "sim:hc-jess", "contact_name": "Teammate C",
     "contact_phone": "env:DEMO_PHONE_C", "parent_phone": "env:DEMO_PHONE_C", "needs": [], "tags": ["demo", "teen"]},
]

# The consumer phone app's persona (mobile/). Appended after the seeded population with its own RNG, so adding it
# does not reshuffle the 250 generated users the stress figures were measured on. Home = the app's trip origin.
APP_PERSONAS: list[dict[str, Any]] = [
    {"id": "hc-dana", "name": "Dana Whitfield", "age": 41, "vehicle": ("Toyota", "RAV4", "suv"),
     "home": (30.01281, -99.1169), "phone": "env:DEMO_PHONE_DANA", "contact_name": "Maria Whitfield",
     "contact_phone": "sim:hc-dana-contact", "needs": [], "tags": ["demo", "commuter", "app"],
     # the live demo phone: danger calls her at once instead of polling first
     "preferred_channel": "voice"},
]
APP_SEED_OFFSET = 1


def _persona_record(rng: random.Random, p: dict[str, Any], points: list[dict]) -> dict:
    prof = _profile(rng, p["id"], p["name"], p["age"], p["vehicle"], p["home"], points, p["needs"], "en")
    if "preferred_channel" in p:   # per-persona override; draws nothing from rng, so other users are unchanged
        prof["policy"]["preferred_channel"] = p["preferred_channel"]
    return {"id": p["id"], "name": p["name"], "age": p["age"], "phone": p["phone"],
            "home": {"lat": p["home"][0], "lon": p["home"][1]}, "contact_name": p["contact_name"],
            "contact_phone": p["contact_phone"], "parent_phone": p.get("parent_phone"),
            "profile": prof, "tags": p["tags"]}


def _jitter(rng: random.Random, lat: float, lon: float, m: float) -> tuple[float, float]:
    r, th = m * math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
    return lat + r * math.cos(th) / M_PER_DEG, lon + r * math.sin(th) / (M_PER_DEG * math.cos(math.radians(lat)))


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * M_PER_DEG
    dx = (a[1] - b[1]) * M_PER_DEG * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def _crossings(rng: random.Random, home: tuple[float, float], points: list[dict]) -> list[dict]:
    near = sorted((p for p in points if _dist_m(home, (p["lat"], p["lon"])) <= CROSSING_RADIUS_M),
                  key=lambda p: _dist_m(home, (p["lat"], p["lon"])))[:3]
    return [{"road": p["name"], "point_id": p["id"], "trips_per_week": rng.randint(2, 12)} for p in near]


def _profile(rng: random.Random, uid: str, name: str, age: int, vehicle: tuple[str, str, str],
             home: tuple[float, float], points: list[dict], needs: list[str] | None, language: str | None) -> dict:
    d = Driver(uid, name, age, Vehicle(*vehicle), 0, f"sim:{uid}", Contact("", "", ""), ())
    prof = build_profile(d, {})
    prof["derived"]["frequent_crossings"] = _crossings(rng, home, points)
    if needs is not None:
        prof["needs"] = needs
    if language:
        prof["policy"]["language"] = language
    return prof


def generate(n: int) -> list[dict]:
    rng = random.Random(SEED)
    data = json.loads((DATA_DIR / "region" / "hill_country" / "nodes.json").read_text())
    nodes, points = data["nodes"], data["points"]
    weights = [max(1, nd["households"]) for nd in nodes]
    out: list[dict] = [_persona_record(rng, p, points) for p in PERSONAS]
    for i in range(n - len(PERSONAS)):
        nd = rng.choices(nodes, weights)[0]
        lat, lon = _jitter(rng, nd["lat"], nd["lon"], JITTER_M)
        older = rng.random() < nd.get("older_share", 0.25)
        age = rng.randint(65, 92) if older else rng.randint(16, 64)
        uid = f"kc-{i:04d}"
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        vehicle = rng.choice(VEHICLES)
        prof = _profile(rng, uid, name, age, vehicle, (lat, lon), points, None, None)
        if older and rng.random() < 0.12:
            prof["needs"] = [rng.choice(["mobility_assist", "wheelchair_user", "powered_medical_equipment"])]
        out.append({"id": uid, "name": name, "age": age, "phone": f"sim:{uid}",
                    "home": {"lat": round(lat, 6), "lon": round(lon, 6)}, "contact_name": f"{rng.choice(FIRST)} {name.split()[1]}",
                    "contact_phone": f"sim:{uid}-contact", "parent_phone": f"sim:{uid}-parent" if age <= 19 else None,
                    "profile": prof, "tags": [nd["kind"], nd["town"]]})
    app_rng = random.Random(SEED + APP_SEED_OFFSET)
    out.extend(_persona_record(app_rng, p, points) for p in APP_PERSONAS)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=250)
    args = ap.parse_args()
    users = generate(args.n)
    atomic_write_json(REGION_USERS_PATH, users)
    print(f"wrote {len(users)} users to {REGION_USERS_PATH}")


if __name__ == "__main__":
    main()
