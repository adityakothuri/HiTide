"""Read-time freshness and collection coverage for the Texas near-live view."""

import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from time import monotonic

from shapely.geometry import mapping, shape

from feeds import Scope, collect_raw
from feeds.intake import RawEnvelope, collect_request
from feeds.nws import ALERTS_REQUEST
from feeds.source_views import LABELS, NOTES, preview
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
    if raw.source_id in LABELS:
        projected = preview(raw)
        if projected is None:
            return "uninterpretable_preview"
        timestamp = _instant(projected.get("time"))
        if timestamp is None:
            return projected.get("time_reason", "unknown_time")
        if timestamp > as_of:
            return "future_time"
        if as_of - timestamp > timedelta(minutes=minutes):
            return "outside_window"
        return None
    if raw.source_id not in {"usgs_gage", "nws_alerts", "nws_local_storm_reports", "drivetexas_work_zones"}:
        return "reference_only"
    props = raw.raw_payload.get("properties") if isinstance(raw.raw_payload, dict) else None
    if not isinstance(props, dict):
        return "missing_properties"
    alert = raw.source_id == "nws_alerts"
    if raw.source_id == "drivetexas_work_zones":
        published = _instant(raw.provider_metadata.get("feed_updated_at"))
        start, end = _instant(props.get("start_date")), _instant(props.get("end_date"))
        if published is None or start is None or end is None:
            return "unknown_time"
        if not start <= as_of < end:
            return "outside_validity"
        if not timedelta(0) <= as_of - published <= timedelta(minutes=minutes):
            return "outside_window"
        return None
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
        context = []
        for raw in batch:
            reason = exclusion_reason(raw, now, minutes)
            if reason is None:
                projected = preview(raw) if raw.source_id in LABELS else None
                records.append({**asdict(raw), "preview": projected} if projected else raw)
            else:
                excluded[reason] += 1
                projected = preview(raw) if raw.source_id in LABELS else None
                if projected and projected.get("evidence_type") == "context":
                    context.append({**asdict(raw), "preview": projected})
        usable = sum(raw.provenance == "live" and raw.retrieval_status in {"success", "empty"} for raw in batch)
        status = "complete" if usable == len(batch) else ("partial" if usable else "unavailable")
        sources[source_id] = {"status": status, "records": records, "context": context,
                              "excluded": dict(excluded), "errors": sorted({e for raw in batch for e in raw.errors}),
                              "label": LABELS.get(source_id), "notes": NOTES.get(source_id)}
    return {"scope": scope, "as_of": now, "max_age_minutes": minutes, "sources": sources}


def map_response(response: dict) -> dict:
    """Keep raw intake on the raw API while sending only display fields to the map."""
    properties = ("monitoring_location_name", "monitoring_location_id", "value", "unit_of_measure",
                  "time", "event", "areaDesc", "headline", "sent", "expires", "city", "county",
                  "remark", "valid", "core_details", "vehicle_impact", "end_date")
    for batch in response["sources"].values():
        for field in ("records", "context"):
            reduced = []
            for raw in batch.get(field, []):
                row = asdict(raw) if isinstance(raw, RawEnvelope) else dict(raw)
                if row.get("preview"):
                    row["raw_payload"] = None
                else:
                    body = row.get("raw_payload") or {}
                    props = body.get("properties") or {}
                    row["raw_payload"] = {"geometry": body.get("geometry"),
                                          "properties": {key: props[key] for key in properties if key in props}}
                    if row["source_id"] == "drivetexas_work_zones" and body.get("geometry"):
                        try:
                            row["raw_payload"]["geometry"] = mapping(shape(body["geometry"]).simplify(0.002))
                        except (TypeError, ValueError, KeyError):
                            row["raw_payload"]["geometry"] = None
                reduced.append(row)
            batch[field] = reduced
    return response
