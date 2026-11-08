"""Drone snapshot: overview.md 9.5 fields (unchanged meaning) + drone vision plan section 8 fields.

Unknowns are null, never 0: water_on_road null = "couldn't see enough road" (fusion ignores it),
est_depth_in null = "no depth measured". depth_method says where a depth came from.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DepthMethod = Literal["water_edge_dem", "none"]
TrendName = Literal["rising", "falling", "steady", "unknown"]
IMAGE_URL_RE = r"^/static/drone/snapshots/[A-Za-z0-9_.-]{1,96}\.jpg$"
ID_RE = r"^[A-Za-z0-9_.-]{1,64}$"
EdgeId = Annotated[str, StringConstraints(max_length=64)]
Reason = Annotated[str, StringConstraints(max_length=120)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class VehicleOut(_Frozen):
    track_id: int = Field(ge=0)
    type: Literal["car", "truck", "bus", "motorcycle", "boat"]
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    in_water: bool | None             # null: water state not visible (frame edge, crowd)
    partly_submerged: bool = False
    depth_at_vehicle_in: float | None = Field(default=None, ge=0, le=600)
    band: Literal["none", "wheels", "doors", "windows", "roof"] | None = None
    band_source: Literal["water_surface"] | None = None
    matched_case_id: str | None = Field(default=None, pattern=ID_RE)


class PersonOut(_Frozen):
    track_id: int = Field(ge=0)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    situation: Literal["in_water", "on_vehicle", "dry_near_water", "dry_away", "unknown"]
    on_vehicle_id: int | None = None


class AlertOut(_Frozen):
    priority: Literal["critical", "high", "medium", "low"]
    kind: str = Field(max_length=40)
    message: str = Field(max_length=200)
    track_id: int | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    depth_in: float | None = Field(default=None, ge=0, le=600)
    boat_required: bool = False
    case_id: str | None = Field(default=None, pattern=ID_RE)


class VisionSnapshot(_Frozen):
    # ---- overview.md 9.5 ----
    point_id: str = Field(pattern=ID_RE)
    time: datetime
    water_on_road: bool | None
    road_covered_pct: float | None = Field(default=None, ge=0, le=100)   # share of the VISIBLE road under water
    est_depth_in: float | None = Field(default=None, ge=0, le=600)
    depth_method: DepthMethod
    rising: bool | None
    people_seen: int = Field(ge=0)
    confidence: Literal["low", "medium", "high"]
    image_url: str | None = Field(default=None, pattern=IMAGE_URL_RE)
    # ---- drone vision plan section 8 ----
    road_visible_pct: float | None = Field(default=None, ge=0, le=100)   # how much of the road the drone saw
    drone_id: str | None = Field(default=None, pattern=ID_RE)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    water_surface_elev_m: float | None = Field(default=None, ge=-500, le=9000)
    water_surface_range_m: tuple[float, float] | None = None
    depth_at_road_range_in: tuple[float, float] | None = None
    depth_band: Literal["shallow", "caution", "dangerous", "vehicles_float", "boat_only"] | None = None
    rise_rate_in_per_hr: float | None = Field(default=None, ge=-2000, le=2000)
    trend: TrendName = "unknown"
    edge_points_used: int = Field(default=0, ge=0, le=1_000_000)
    edge_sides: int = Field(default=0, ge=0, le=2)
    vehicles: list[VehicleOut] = Field(default_factory=list, max_length=50)
    people: list[PersonOut] = Field(default_factory=list, max_length=50)
    alerts: list[AlertOut] = Field(default_factory=list, max_length=100)
    spread_segments: list[EdgeId] = Field(default_factory=list, max_length=500)
    confidence_reasons: list[Reason] = Field(default_factory=list, max_length=20)
    source: Literal["synthetic", "video", "photo", "live"] = "synthetic"
    simulated: bool = True

    @model_validator(mode="after")
    def _consistent(self) -> VisionSnapshot:
        if self.time.tzinfo is None:
            raise ValueError("time must include a UTC offset")
        if self.people_seen != len(self.people):
            raise ValueError("people_seen must equal len(people)")
        if self.depth_method == "none" and self.est_depth_in is not None:
            raise ValueError("est_depth_in requires a depth_method")
        if self.depth_method != "none" and self.est_depth_in is None:
            raise ValueError("depth_method set but est_depth_in missing")
        if self.water_on_road is False and self.est_depth_in not in (None, 0):
            raise ValueError("a dry road can't have a depth")
        for rng in (self.water_surface_range_m, self.depth_at_road_range_in):
            if rng is not None and rng[0] > rng[1]:
                raise ValueError("range low must be <= high")
        if self.rising is not None and self.rising != (self.trend == "rising"):
            raise ValueError("rising must agree with trend")
        return self
