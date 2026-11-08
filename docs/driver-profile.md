# Driver Flood-Risk Profile

Design for the per-driver profile behind the three HiTide stages (pre-trip warning, en-route turn-around, stopped-in-water escalation).

**Status:** design only. We have **no authorized access** to State Farm customer data. Every State Farm field below is **simulated** in the demo and labeled that way. The field list mirrors what State Farm publicly documents so the integration is realistic.

## Purpose and limits

The profile answers one question: *if a flood hits, how likely is this driver to be in danger, and how fast can we reach them?*

Hard rules:

1. **Protection only.** No profile field or output may feed pricing, underwriting, or claims decisions. Our process reads State Farm data and never writes back to it.
2. **Needs only raise priority.** Age, disability, and medical fields can make help come sooner or change the alert channel. They can never lower priority or exclude anyone.
3. **Opt-in.** Flood alerts and location sharing need their own consent, modeled on Accident Assistance (separate opt-in, can be turned off).
4. **Store needs, not diagnoses.** "Needs help to evacuate", not the medical condition.
5. **Share with responders only on escalation.** Never in advance, never in bulk.
6. **Never used:** race, religion, gender or sex, income, credit, life and health insurance data.
7. **Coarse bands in the UI.** Follow the existing contract rule: `urgency_reasons` use bands like "older driver (65+)", never exact age or model.

## Source tags

Every field carries a `source` tag so judges and reviewers can see what is real, what is ours, and what needs State Farm sign-off.

| Tag | Meaning | Real or simulated in demo |
|---|---|---|
| `sf_dss` | Drive Safe & Save telematics, as documented | Simulated |
| `sf_steer_clear` | Steer Clear (young-driver program) | Simulated |
| `sf_policy` | Auto/home/renters policy and application data | Simulated |
| `sf_claims` | State Farm internal claims history | Simulated |
| `sf_live` | Live State Farm signals (roadside request, Accident Assistance event, app health check) | Simulated |
| `sf_adt` | ADT Home Alert Protection data (opted-in homeowners only) | Simulated |
| `derived` | Computed by us from the fields above | Computed |
| `public` | Public data (FEMA, NWS, USGS, OSM) | Real where we have it |
| `self_reported` | Entered by the customer, opt-in | Simulated |

## 1. Driving: Drive Safe & Save (`sf_dss`) and Steer Clear

Based on the [Drive Safe & Save FAQ](https://www.statefarm.com/customer-care/faqs/drive-safe-save.html), the [program page](https://www.statefarm.com/drivesafeandsave), and the [State Farm EULA](https://www.statefarm.com/general/end-user-licensing-agreement).

| Field | Documented basis |
|---|---|
| `trips[]`: start/end time, route (precise GPS while driving), speed, miles | EULA: "precise location while driving", "trip information (date and time, speed, miles driven, etc.)" |
| `trips[].events[]`: `speeding`, `hard_braking`, `fast_acceleration`, `sharp_cornering`, `phone_distraction` | FAQ event definitions. Speeding = 8+ mph over the posted limit. Phone distraction = vehicle moving + phone moving in vehicle + screen on. |
| `score_14d` | 14-day driving score per phone (not the premium adjustment) |
| `beacon_id`, `vehicle_id` | Beacon is tied to one vehicle; it has **no GPS**. When several phones are in the car, only the first to connect records the trip. |
| `annual_mileage` | Odometer readings (setup, and about every 6 months in some states) |
| `app_health`: last daily signal, location "Always", motion, Bluetooth on | FAQ: app sends a daily signal; missed days trigger an email. Required permissions. |
| `accident_assistance_enabled` | Separate opt-in in the app |
| `steer_clear_enrolled` | Steer Clear app for young drivers |

Documented limits we must respect:

- **Location exists only during trips** and comes from the phone. There is no parked-car location.
- **Customer-visible history is 30 days.** The premium uses up to 12 months. Internal retention is not stated.
- **On Android, trips record even when the person is a passenger.** Per-driver behavior is noisy: the "driver" is whoever's phone recorded.
- Named insureds see all trips on the policy. Additional drivers see only their own trips. Domestic-abuse victims can restrict display.

## 2. Derived from trips (`derived`)

| Field | How |
|---|---|
| `frequent_crossings[]`: crossing id, trips per week | Trip routes overlaid on our low-water crossing layer |
| `home_area`, `work_area` | Clustered trip start/end points (kept as an area, not a point trail) |
| `night_driving_share` | Share of miles driven at night |
| `speeding_per_100mi`, `distraction_per_100mi` | Event counts divided by miles |
| `drove_during_past_alerts` | Trips matched to NWS alert history (limited by available history) |
| `last_known_location`, `location_age_s` | Latest trip point, only while driving |

## 3. Policy and claims (`sf_policy`, `sf_claims`)

Based on the [State Farm Notice of Privacy Policy](https://www.statefarm.com/customer-care/privacy-security/privacy), which lists applications, conversations, app use, and consumer reporting agencies ("driving records") as sources.

| Field | Source | Why it matters |
|---|---|---|
| `age_band` (from date of birth) | `sf_policy` | 70+ are slower to get out of a stranded car and more often hurt |
| `years_licensed`, `new_driver` | `sf_policy` | Less experience judging water on the road |
| `driving_record_flags` | `sf_policy` (consumer reporting agencies) | Light input only |
| `vehicle`: make, model, year | `sf_policy` | Feeds clearance lookup |
| `vehicle.clearance_in`, `vehicle.stall_depth_in` | `derived` from model | Sedans can stall in about 12 in of water, trucks about 24 in |
| `household_drivers[]`, `named_insured` | `sf_policy` | Who else to alert, and who may see which trips |
| `garaging_address` area | `sf_policy` | Home flood exposure |
| `contact`: phone, email, preferred channel, language | `sf_policy` | How to reach them |
| `other_policies`: home, renters, home type (e.g. mobile home) | `sf_policy` | Home exposure, especially manufactured homes |
| `has_flood_coverage` | `sf_policy` | Signals they know the home is at risk |
| `past_flood_claims[]`: date, type (home water, vehicle flood total) | `sf_claims` | Real past exposure. **Flood/water claims only.** |
| `agent`: assigned agent id and office phone | `sf_policy` | Trusted person for welfare calls |

## 4. Live State Farm signals (`sf_live`, `sf_adt`)

These are the strongest State Farm-only signals that someone is in trouble.

| Signal | Basis | Use |
|---|---|---|
| Roadside assistance request near a warned area | App roadside requests; State Farm directs customers to the app in disasters ([Hurricane Beryl release](https://newsroom.statefarm.com/state-farm-responds-to-hurricane-beryl/)) | Strong "stuck in water" signal → escalate |
| Accident Assistance event | Detects a likely crash, can contact emergency and tow services ([newsroom](https://newsroom.statefarm.com/new-era-of-road-safety/)) | Escalate; reuse its consent model |
| ADT water sensor alert at home | Opted-in homeowners shared ADT account and usage data (no audio/video); packages included 3–7 water sensors ([ADT terms](https://www.adt.com/about-adt/legal/statefarm-promotional-water-terms)). The program has been [scaled back](https://coverager.com/state-farm-scales-back-its-smart-home-bet-on-adt/). | Direct evidence of water at the home. Optional, opted-in customers only. |
| App daily health check missed | FAQ | Lower confidence in "no trip" meaning "not driving" |

## 5. Self-reported needs (`self_reported`, opt-in, protection only)

| Need | Response change |
|---|---|
| Hearing loss | Text, flashing app alert, vibration instead of a voice call |
| Low vision | Voice call first, large clear audio |
| Uses a wheelchair or has trouble walking | Responders get priority sooner; flag that a lift or boat is needed |
| Memory or thinking difficulty | Alert the family contact at the same time as the driver |
| Depends on powered medical equipment | Higher priority if stranded |
| Pregnant | Higher priority |
| Service animal | Note passed to responders |
| Kids, car seats, or elderly passengers often aboard | Getting everyone out takes longer |
| Pets | People often won't leave without them |
| People at home who can't drive | They depend on this driver to evacuate |
| New to the area | Doesn't know local crossings |
| Emergency and family contacts | For the family stage |
| Consent: flood alerts, share location with responders on escalation, drone check | Required before any of the above is used |

Real-world model: Texas runs the voluntary **State of Texas Emergency Assistance Registry (STEAR)** with 2-1-1 Texas for people who need help in a disaster. Verify the details before citing it in the pitch.

## 6. Public data (`public`)

FEMA flood zone for home and work areas, NWS alerts, USGS gauges upstream of frequent crossings, low ground around home (3DEP), last-exit risk from our connectivity analysis, and cell coverage along routes.

## Profile shape

Two parts:

- **Baseline** (recomputed weekly): route exposure, vehicle vulnerability, behavior tendencies, reachability, household, needs.
- **Live state** (recomputed about every minute during an event): driving or not, distance to the nearest warned crossing, location age, live signals, alert status.

Every factor that raises urgency produces a plain-language reason with its source tag, for example `"uses Cypress Creek crossing ~9×/week" (derived)`, `"low-clearance vehicle" (sf_policy)`. No invented confidence percentage.

```json
{
  "driver_id": "d-014",
  "simulated": true,
  "consent": {"flood_alerts": true, "share_location_on_escalation": true, "drone_check": true, "source": "self_reported"},
  "baseline": {
    "age_band": {"value": "70+", "source": "sf_policy"},
    "vehicle": {"model_class": "sedan", "stall_depth_in": 12, "source": "sf_policy"},
    "frequent_crossings": [{"crossing_id": "x-cypress-01", "trips_per_week": 9, "source": "derived"}],
    "night_driving_share": {"value": 0.35, "source": "derived"},
    "score_14d": {"value": 82, "source": "sf_dss"},
    "past_flood_claims": [{"year": 2025, "type": "vehicle_flood_total", "source": "sf_claims"}],
    "needs": [{"need": "mobility_assist", "source": "self_reported"}],
    "alert_channel_order": ["voice", "sms", "app"],
    "agent_id": "agent-ker-03"
  },
  "live": {
    "driving": true,
    "last_known_location": {"lat": 30.04, "lon": -99.14, "age_s": 20, "source": "derived"},
    "nearest_warned_crossing_m": 600,
    "signals": [{"kind": "roadside_request", "ts": "...", "source": "sf_live"}]
  },
  "urgency_reasons": [
    {"text": "older driver (70+)", "source": "sf_policy"},
    {"text": "low-clearance vehicle", "source": "sf_policy"},
    {"text": "uses a warned crossing often", "source": "derived"},
    {"text": "needs help to evacuate", "source": "self_reported"}
  ]
}
```

## Implementation

- Built by `backend/sim/profiles.py`, stored as a `profile` block on each driver in `data/drivers.json`, and loaded into `Driver.profile` by `backend/sim/drivers.py`.
- Regenerate profiles without changing routes: `cd backend && uv run python -m scripts.gen_profiles`. `scripts.gen_drivers` also attaches profiles.
- Seeded per driver id, so output is repeatable.
- Source tags are per section (`profile.sources`, e.g. `dss → sf_dss`), not per field, to keep the file readable. `profile.simulated` is always `true`.
- "Frequent crossings" use the lowest 2% of road-segment elevations as a stand-in for low-water crossings, with the top 3 roads kept per driver. This is a placeholder until a real crossing layer exists.
- `profile` is backend-only. It is not in `DriverPublic` or any frontend payload.
- Scoring: when a stopped-in-water case opens, `scoring/risk.py` `profile_risk_fields()` adds four factors that can only raise urgency: evacuation need, new to the area, phone-distraction rate, and live signals (roadside request, ADT water sensor). Weights live in `backend/config/weights.yaml`. Reasons stay coarse, such as "needs extra help (self-reported)". Channel choice from needs (for example SMS first for hearing loss) is not wired yet.
- Personas: `demo-d` (70+, sedan, night driving, mobility need, past flood total), `demo-t` (Steer Clear teen), `d-005` (wheelchair user), `d-010` and `d-060` (Spanish; `d-060` new to the area), `d-020` (ADT water sensor trips at about minute 30), `d-030` (roadside request at about minute 38), `d-040` (hearing loss, SMS first), `d-050` (powered medical equipment at home).

## Relation to existing data

`data/drivers.json` keeps `age`, `vehicle {make, model, type}`, `home_node`, `phone` (env reference), `emergency_contact`, `parent`, and `routes[].edge_ids` (the stand-in for DSS trip routes), because the legacy simulator and risk scoring read them.

- `sex` was **removed**. Nothing read it, and it conflicts with rule 6.
- Exact `age` stays in the backend file for scoring. The frontend still only sees bands via `urgency_reasons`.

Any payload change goes into `docs/api-contract.md` first.

## Demo personas

15–20 simulated Kerrville drivers, including at least:

- An older driver (70+) in a sedan who drives a low-water crossing at night.
- A teen enrolled in Steer Clear, with parents as contacts.
- A driver who uses a wheelchair.
- A Spanish-speaking driver.
- A homeowner with an ADT water sensor that trips during the event.
- A driver whose roadside request inside the warned area triggers escalation.

## Open questions

- Whether the HackUTD State Farm track provides any sample data.
- The full Drive Safe & Save program consent text (emailed per state after enrollment; not public).
- State Farm's drone program status after its national FAA waiver ended in Nov 2022.

## Sources

- [Drive Safe & Save FAQ](https://www.statefarm.com/customer-care/faqs/drive-safe-save.html)
- [Drive Safe & Save program page](https://www.statefarm.com/drivesafeandsave)
- [State Farm End User License Agreement](https://www.statefarm.com/general/end-user-licensing-agreement)
- [State Farm Notice of Privacy Policy](https://www.statefarm.com/customer-care/privacy-security/privacy)
- [State Farm newsroom: Accident Assistance](https://newsroom.statefarm.com/new-era-of-road-safety/)
- [Carrier Management: accident detection expansion](https://www.carriermanagement.com/news/2025/10/21/280632.htm)
- [State Farm Hurricane Beryl response](https://newsroom.statefarm.com/state-farm-responds-to-hurricane-beryl/)
- [ADT water leak program terms for State Farm customers](https://www.adt.com/about-adt/legal/statefarm-promotional-water-terms)
- [Coverager: State Farm scales back ADT](https://coverager.com/state-farm-scales-back-its-smart-home-bet-on-adt/)
- [WGLT: FAA's first national drone waiver to State Farm](https://www.wglt.org/science-and-technology/2019-01-10/state-farm-earns-faas-first-national-drone-waiver)
- [Inside Unmanned Systems: Hurricane Florence waiver](https://insideunmannedsystems.com/state-farm-receives-waiver-from-faa-for-hurricane-florence-response/)
