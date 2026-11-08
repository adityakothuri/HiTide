"""Raw record handoff. Collection has no dependencies on interpretation or storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from feeds.base import RecordShape, Source, fetch_with_fallback, response_records


@dataclass(frozen=True)
class FeedRequest:
    source_id: str
    product: str
    url: str
    params: dict
    geographic_scope: dict
    shape: RecordShape
    timeout_s: float = 5.0


@dataclass(frozen=True)
class RawEnvelope:
    source_id: str
    source_record_id: str | None
    attempt_id: str
    retrieved_at: str
    payload_retrieved_at: str | None
    request_params: dict
    geographic_scope: dict
    provider_metadata: dict
    raw_payload: Any
    provenance: Source
    retrieval_status: Literal["success", "empty", "malformed", "failed"]
    errors: tuple[str, ...]
    record_index: int | None = None


class IntakeConsumer(Protocol):
    """A later normalizer receives one raw envelope or attempt marker at a time."""

    async def receive(self, envelope: RawEnvelope) -> None: ...


def split_response(
    request: FeedRequest, response: dict, *, retrieved_at: str | None = None
) -> list[RawEnvelope]:
    """Extract record boundaries only. Preserve invalid entries for later quarantine."""
    payload = response["data"]
    headers = response.get("provider_metadata")
    metadata = {
        k: headers[k]
        for k in ("content-type", "etag", "last-modified", "date", "http_status")
        if isinstance(headers, dict) and k in headers
    }
    endpoint = urlsplit(request.url)
    metadata.update(
        product=request.product,
        endpoint=f"{endpoint.scheme}://{endpoint.hostname}{endpoint.path}",
    )
    if isinstance(payload, dict):
        context = payload.get("@context")
        contexts = context if isinstance(context, list) else [context]
        for entry in contexts:
            if isinstance(entry, dict) and type(entry.get("@version")) in (int, float):
                metadata["jsonld_version"] = entry["@version"]
                break
        for key in ("numberReturned", "numberMatched", "timeStamp", "updated"):
            if key in payload:
                metadata[key] = payload[key]
        links = payload.get("links")
        if isinstance(links, list):
            metadata["has_next_page"] = any(
                isinstance(link, dict) and link.get("rel") == "next" for link in links
            )
        pagination = payload.get("pagination")
        if isinstance(pagination, dict) and pagination.get("next"):
            metadata["has_next_page"] = True
    # A closed set of public query parameters excludes headers and arbitrary credentials.
    public_keys = (
        "area",
        "state_code",
        "sts",
        "ets",
        "states",
        "point",
        "event",
        "monitoring_location_id",
        "parameter_code",
        "f",
        "time",
        "limit",
    )
    common = {
        "source_id": request.source_id,
        "attempt_id": str(uuid4()),
        "retrieved_at": retrieved_at or datetime.now(UTC).isoformat(),
        "payload_retrieved_at": response.get("fetched_at"),
        "provenance": response["source"],
        "request_params": {k: v for k, v in request.params.items() if k in public_keys},
        "geographic_scope": dict(request.geographic_scope),
        "provider_metadata": metadata,
    }
    errors = tuple(response.get("errors", ()))
    records = response_records(payload, request.shape)
    if response["source"] == "unavailable":
        return [
            RawEnvelope(
                **common,
                source_record_id=None,
                raw_payload=None,
                retrieval_status="failed",
                errors=errors,
            )
        ]
    if not isinstance(records, list):
        return [
            RawEnvelope(
                **common,
                source_record_id=None,
                raw_payload=payload,
                retrieval_status="malformed",
                errors=(*errors, "unexpected_response_shape"),
            )
        ]
    if not records:
        return [
            RawEnvelope(
                **common,
                source_record_id=None,
                raw_payload=payload,
                retrieval_status="empty",
                errors=errors,
            )
        ]
    result = []
    for index, record in enumerate(records):
        record_id = None
        if isinstance(record, dict):
            record_id = record.get("id")
            if request.source_id == "nws_alerts" and isinstance(
                record.get("properties"), dict
            ):
                record_id = record["properties"].get("id") or record_id
        valid = isinstance(record, dict)
        result.append(
            RawEnvelope(
                **common,
                record_index=index,
                source_record_id=str(record_id)
                if type(record_id) in (str, int)
                else None,
                raw_payload=record,
                retrieval_status="success" if valid else "malformed",
                errors=errors if valid else (*errors, "unexpected_record_shape"),
            )
        )
    return result


async def collect_request(
    request: FeedRequest, *, cache_only: bool = False
) -> list[RawEnvelope]:
    response = await fetch_with_fallback(
        request.product,
        request.url,
        request.params,
        request.timeout_s,
        cache_only=cache_only,
        shape=request.shape,
    )
    return split_response(request, response)
