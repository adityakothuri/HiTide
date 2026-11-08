"""Temporary, narrow NWS warning projection for the flood-monitor demonstration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from evidence.flood_monitor import AcceptedFloodWarning
from feeds.intake import RawEnvelope


@dataclass(frozen=True)
class DemoDecision:
    reason: str
    observation: AcceptedFloodWarning | None = None


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("missing timestamp")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("missing timezone")
    return stamp.astimezone(UTC)


def project_warning(raw: RawEnvelope) -> DemoDecision:
    """Only original Actual flood warnings with an explicit validity window qualify."""
    if raw.source_id != "nws_alerts":
        return DemoDecision("outside_demo_source")
    if raw.retrieval_status != "success":
        return DemoDecision(raw.retrieval_status)
    feature = raw.raw_payload
    if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
        return DemoDecision("malformed_feature")
    props = feature["properties"]
    for field in ("status", "messageType", "event"):
        if not isinstance(props.get(field), str) or not props[field].strip():
            return DemoDecision(f"missing_{field}")
    if props["status"] != "Actual":
        return DemoDecision("outside_demo_status")
    if props["messageType"] != "Alert":
        return DemoDecision("unsupported_message_type")
    if props["event"] not in ("Flood Warning", "Flash Flood Warning"):
        return DemoDecision("outside_demo_warning_type")
    if not isinstance(raw.source_record_id, str) or not raw.source_record_id.strip():
        return DemoDecision("missing_provider_id")
    try:
        start = max(_timestamp(props.get("sent")), _timestamp(props.get("effective")))
        end = _timestamp(props.get("expires"))
    except (TypeError, ValueError, OverflowError):
        return DemoDecision("invalid_provider_time")
    if end <= start:
        return DemoDecision("invalid_validity_interval")
    # Replaying the same issuer message/interval yields the same demo revision ID.
    identity = (
        f"{raw.source_id}|{raw.source_record_id}|{start.isoformat()}|{end.isoformat()}"
    )
    obs_id = f"demo-obs:{uuid5(NAMESPACE_URL, identity)}"
    return DemoDecision("accepted_for_demo", AcceptedFloodWarning(obs_id, start, end))
