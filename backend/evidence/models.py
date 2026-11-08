"""Validated observations shared by ingestion, local reports, and drone results."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def aware_time(value: str | None) -> str | None:
    if value is None:
        return None
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return stamp.astimezone(UTC).isoformat()


class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, max_length=120)
    source_id: str = Field(min_length=1, max_length=120)
    source_record_id: str = Field(min_length=1, max_length=300)
    observed_at: str | None = None
    ingested_at: str | None = None
    valid_until: str | None = None
    kind: Literal["closure", "report", "gauge", "warning", "weather", "drone"]
    road_id: str | None = Field(default=None, max_length=200)
    geometry: dict[str, Any] | None = None
    value: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    access: Literal["open", "closed", "restricted", "unknown"] = "unknown"
    quality: Literal["unverified", "agency", "sensor", "operator"] = "unverified"
    simulated: bool = False
    source_mode: Literal["live", "cached", "unavailable", "simulated", "manual"] = "manual"
    raw: dict[str, Any] = Field(default_factory=dict)
    supersedes_id: str | None = None

    @field_validator("observed_at", "ingested_at", "valid_until")
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        return aware_time(value)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("measurement must be finite")
        return value

    @field_validator("geometry")
    @classmethod
    def geojson(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        depths = {"Point": 0, "MultiPoint": 1, "LineString": 1, "MultiLineString": 2,
                  "Polygon": 2, "MultiPolygon": 3}
        kind = value.get("type")
        if kind not in depths:
            raise ValueError("geometry must be a GeoJSON point, line, or polygon")

        def check(coords: Any, depth: int) -> None:
            if not isinstance(coords, (list, tuple)) or not coords:
                raise ValueError("geometry coordinates cannot be empty")
            if depth:
                for part in coords:
                    check(part, depth - 1)
            else:
                if len(coords) < 2:
                    raise ValueError("coordinates require longitude and latitude")
                lon, lat = coords[:2]
                if isinstance(lon, bool) or isinstance(lat, bool) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                    raise ValueError("coordinates must be numbers")
                if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("longitude or latitude is out of range")

        check(value.get("coordinates"), depths[kind])
        return value

    @model_validator(mode="after")
    def measurement_rules(self) -> ObservationIn:
        if self.value is not None and not self.unit:
            raise ValueError("measurements require an explicit unit")
        if self.kind == "gauge" and self.access != "unknown":
            raise ValueError("a gauge reading cannot directly establish road access")
        if self.kind == "gauge" and self.value is None:
            raise ValueError("a gauge observation requires a numeric reading")
        if self.observed_at and datetime.fromisoformat(self.observed_at) > datetime.now(UTC) + timedelta(minutes=10):
            raise ValueError("observation time is more than ten minutes in the future")
        return self
