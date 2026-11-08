"""Evidence and mission API. Synchronous SQLite work runs in FastAPI's thread pool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import require_trusted_origin
from evidence.models import ObservationIn, aware_time
from evidence.service import EvidenceService

router = APIRouter(prefix="/api/evidence", tags=["Evidence and inspections"], dependencies=[Depends(require_trusted_origin)])


def service(request: Request) -> EvidenceService:
    return request.app.state.evidence


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    road_id: str = Field(min_length=1, max_length=200)
    observed_at: str
    access: Literal["open", "closed", "restricted", "unknown"] = "unknown"
    source_record_id: str | None = Field(default=None, max_length=300)
    raw: dict[str, Any] = Field(default_factory=dict)
    # Accept only unverified community-report attributes; callers cannot elevate trust.
    source_id: Literal["local_reports"] = "local_reports"
    kind: Literal["report"] = "report"
    quality: Literal["unverified"] = "unverified"
    simulated: bool = False

    @field_validator("observed_at")
    @classmethod
    def report_time(cls, value: str) -> str:
        normalized = aware_time(value)
        if datetime.fromisoformat(normalized) > datetime.now(UTC) + timedelta(minutes=10):
            raise ValueError("Observation is more than ten minutes in the future")
        return normalized


class CompletionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["open", "closed", "inconclusive"]
    observed_at: str
    image_url: str | None = Field(default=None, max_length=2000)
    water_depth_in: float | None = Field(default=None, ge=0, le=1200, allow_inf_nan=False)

    @field_validator("observed_at")
    @classmethod
    def completion_time(cls, value: str) -> str:
        return ReportIn.report_time(value)

    @field_validator("image_url")
    @classmethod
    def safe_image_reference(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("/static/drone/", "https://")):
            raise ValueError("Image reference must be HTTPS or a /static/drone/ asset")
        return value


class IntersectionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    geometry: dict[str, Any]

    @field_validator("geometry")
    @classmethod
    def valid_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        return ObservationIn.geojson(value)


class GraphLocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    node_id: str = Field(min_length=1, max_length=120)


class CommunityIn(GraphLocationIn):
    households: int | None = Field(default=None, ge=0, le=1000000)


class ConfigurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    communities: list[CommunityIn] = Field(max_length=100)
    destinations: list[GraphLocationIn] = Field(max_length=100)


def translate_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, KeyError) else 409, detail=str(exc).strip("'"))


@router.get("/state")
def state(request: Request) -> dict:
    return service(request).snapshot()


@router.get("/health")
def health(request: Request) -> dict:
    return service(request).store.diagnostics()


@router.get("/nearby")
def nearby(request: Request, lon: float = Query(ge=-180, le=180), lat: float = Query(ge=-90, le=90), radius_m: float = Query(default=1000, gt=0, le=50000)) -> dict:
    store = service(request).store
    if not hasattr(store, "nearby_observations"):
        raise HTTPException(status_code=501, detail="Nearby search requires the MongoDB geospatial store")
    return {"observations": store.nearby_observations(lon, lat, radius_m)}


@router.post("/intersections")
def intersections(body: IntersectionsIn, request: Request) -> dict:
    store = service(request).store
    if not hasattr(store, "intersecting_roads"):
        raise HTTPException(status_code=501, detail="Intersection search requires the MongoDB geospatial store")
    return {"roads": store.intersecting_roads(body.geometry)}


@router.post("/reports")
def reports(body: ReportIn, request: Request) -> dict:
    try:
        return service(request).add_report(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ingest")
async def ingest(request: Request) -> dict:
    return await service(request).ingest()


@router.post("/demo")
def demo(request: Request) -> dict:
    return service(request).start_demo()


@router.post("/town")
def town(request: Request) -> dict:
    return service(request).use_town(request.app.state.runtime.town)


@router.post("/configuration")
def configuration(body: ConfigurationIn, request: Request) -> dict:
    try:
        return service(request).configure([c.model_dump(exclude_none=True) for c in body.communities], [d.model_dump() for d in body.destinations])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/assign")
def assign(task_id: str, request: Request) -> dict:
    try:
        return service(request).assign(task_id)
    except (ValueError, KeyError) as exc:
        raise translate_error(exc) from exc


@router.post("/tasks/{task_id}/complete")
def complete(task_id: str, body: CompletionIn, request: Request) -> dict:
    try:
        return service(request).complete(task_id, body.model_dump(exclude_none=True))
    except (ValueError, KeyError) as exc:
        raise translate_error(exc) from exc
