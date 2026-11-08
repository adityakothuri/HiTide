"""Read-time freshness and collection coverage for the Texas near-live view."""

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
from time import monotonic

from feeds import Scope, collect_raw
from feeds.intake import RawEnvelope, collect_request
from feeds.nws import ALERTS_REQUEST
from feeds.texas_roads import road_report_exclusion
from feeds.usgs_ogc import LATEST_REQUEST


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
        return timestamp if timestamp.utcoffset() is not None else None
    except ValueError:
        return None


def exclusion_reason(raw: RawEnvelope, as_of: datetime, minutes: int) -> str | None:
    """Use the provider's observation or issue time, independently of fetch time."""
    if raw.provenance != "live":
        return raw.provenance
    if raw.retrieval_status != "success":
        return raw.retrieval_status
    if raw.source_id not in {"usgs_gage", "nws_alerts", "nws_local_storm_reports"}:
        return "reference_only"
    props = raw.raw_payload.get("properties") if isinstance(raw.raw_payload, dict) else None
    if not isinstance(props, dict):
        return "missing_properties"
    alert = raw.source_id == "nws_alerts"
    field = "sent" if alert else "time"
    if raw.source_id == "nws_local_storm_reports":
        reason = road_report_exclusion(raw)
        if reason:
            return reason
        field = "valid"
    timestamp = _instant(props.get(field))
    if timestamp is None:
        return "unknown_time"
    age = as_of - timestamp
    if age < timedelta(0):
        return "future_time"
    if age > timedelta(minutes=minutes):
        return "outside_window"
    if alert:
        if props.get("status") != "Actual" or props.get("messageType") not in ("Alert", "Update"):
            return "inactive_message"
        if "flood" not in str(props.get("event", "")).lower():
            return "other_hazard"
        start, end = _instant(props.get("effective")), _instant(props.get("expires"))
        if start is None or end is None or not start <= as_of < end:
            return "outside_validity"
    return None


async def collect_recent_inputs(scope: Scope) -> list[RawEnvelope]:
    if scope == "texas":
        return await collect_raw(scope=scope)
    if scope != "kerrville":
        raise ValueError("Unknown monitoring scope")
    alerts, gages = await asyncio.gather(collect_request(ALERTS_REQUEST), collect_request(LATEST_REQUEST))
    return alerts + gages


class RecentSnapshot:
    """Share a single poll across clients and reevaluate evidence age on every read."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._expires = 0.0
        self._records: list[RawEnvelope] = []

    async def read(self, scope: Scope) -> list[RawEnvelope]:
        async with self._lock:
            if monotonic() >= self._expires:
                self._records = await collect_recent_inputs(scope)
                self._expires = monotonic() + 60
            return self._records


async def recent_feeds(minutes: int = 30, scope: Scope = "texas", snapshot: RecentSnapshot | None = None) -> dict:
    if not 15 <= minutes <= 30:
        raise ValueError("freshness window must be between 15 and 30 minutes")
    inputs = await snapshot.read(scope) if snapshot else await collect_recent_inputs(scope)
    now = datetime.now(UTC)
    sources = {}
    for source_id in dict.fromkeys(raw.source_id for raw in inputs):
        batch = [raw for raw in inputs if raw.source_id == source_id]
        excluded = Counter()
        records = []
        for raw in batch:
            reason = exclusion_reason(raw, now, minutes)
            if reason is None:
                records.append(raw)
            else:
                excluded[reason] += 1
        usable = sum(raw.provenance == "live" and raw.retrieval_status in {"success", "empty"} for raw in batch)
        status = "complete" if usable == len(batch) else ("partial" if usable else "unavailable")
        sources[source_id] = {"status": status, "records": records, "excluded": dict(excluded)}
    return {"scope": scope, "as_of": now, "max_age_minutes": minutes, "sources": sources}
