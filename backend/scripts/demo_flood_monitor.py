"""Replay a public warning or evaluate live Texas NWS warnings."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime

from app.config import REPO_DIR
from evidence.demo_warning_parser import project_warning
from evidence.flood_monitor import DemoFloodMonitor
from feeds.intake import RawEnvelope, split_response
from feeds.nws import ALERTS_REQUEST
from feeds.texas import collect_texas_alerts
from feeds.recent import exclusion_reason

EXAMPLE = REPO_DIR / "docs" / "examples" / "map-data" / "nws-flood-warning.json"
EXAMPLE_RETRIEVED = "2026-11-08T03:32:45.125871+00:00"


def example_records() -> list[RawEnvelope]:
    request = replace(
        ALERTS_REQUEST,
        params={"event": "Flood Warning"},
        geographic_scope={"country": "US"},
    )
    with EXAMPLE.open(encoding="utf-8-sig") as file:
        payload = json.load(file)
    return split_response(
        request, {"source": "cached", "fetched_at": EXAMPLE_RETRIEVED, "data": payload}
    )


async def run(live: bool) -> dict:
    envelopes = await collect_texas_alerts() if live else example_records()
    as_of = datetime.now(UTC) if live else datetime.fromisoformat(EXAMPLE_RETRIEVED)
    monitor = DemoFloodMonitor()
    reasons: Counter[str] = Counter()
    accepted = []
    for envelope in envelopes:
        if live and envelope.provenance == "cached":
            reasons["cached_fallback_excluded_from_live_demo"] += 1
            continue
        if live:
            reason = exclusion_reason(envelope, as_of, 30)
            if reason:
                reasons[reason] += 1
                continue
        decision = project_warning(envelope)
        reasons[decision.reason] += 1
        if decision.observation:
            accepted.append(decision.observation)
    transitions = monitor.evaluate(accepted, as_of=as_of)
    if accepted and not live:
        # Advance the replay clock, including when the next poll returns no rows.
        transitions.extend(
            monitor.evaluate([], as_of=max(as_of, *(o.valid_until for o in accepted)))
        )
    return {
        "mode": "live_texas" if live else "historical_example_replay",
        "state_storage": "temporary_in_memory",
        "as_of": as_of.isoformat(),
        "provenance_counts": dict(Counter(e.provenance for e in envelopes)),
        "decision_counts": dict(reasons),
        "transitions": [
            {**asdict(transition), "evaluated_at": transition.evaluated_at.isoformat()}
            for transition in transitions
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Evaluate active alerts across Texas once at the current time.",
    )
    print(json.dumps(asyncio.run(run(parser.parse_args().live)), indent=2))
