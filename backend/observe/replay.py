"""July 4, 2025 replay as an observation provider: exactly the evidence the replay always used.

Warnings: the real NWS timeline from the region yaml (county-wide, so they carry the region's zones).
Rain: the NWS EWX report window (> 1 in/hr west of the cutoff longitude), expressed per critical point.
Gauges: the loop's replay RegionFlood (hydro=None means "unchanged").
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from observe.alerts import Alert
from observe.frame import ObservationFrame, SourceStatus
from sim.region_flood import epoch

REPLAY_HEAVY_IN_HR = 2.0   # inside the reported window; the report gives 4-5 in/hr peaks, so any value > 1 is honest


class ReplayObservations:
    mode = "replay"

    def __init__(self, cfg: dict, points: Mapping[str, dict]):
        zones = frozenset(cfg.get("nws_zones", ()))
        self.alerts = tuple(
            Alert(id=f"replay-{i + 1}", event=w["event"], level="warning",
                  headline=f"REPLAY of July 4, 2025: {w['event']} for {w['area']}", effective=epoch(w["at"]),
                  expires=None, zones=zones, emergency="Emergency" in w["event"], simulated=True, source="replay",
                  sent=w["at"], area=w["area"])
            for i, w in enumerate(cfg["replay"]["warnings"]))
        rain = cfg.get("heavy_rain") or {}
        self.rain_window = (epoch(rain["from"]), epoch(rain["to"])) if rain else None
        west = rain.get("west_of_lon", 999)
        self.rain_points = frozenset(pid for pid, p in points.items() if p["lon"] < west)
        self.point_ids = tuple(points)
        self.sources = MappingProxyType({
            name: SourceStatus("ok", "replay", detail=detail) for name, detail in (
                ("nws_alerts", "Real NWS/county warning times, July 4, 2025"),
                ("usgs_gage", "Real USGS gage height, July 4, 2025 (Hunt gauge dies 05:10 CDT)"),
                ("rain", "NWS EWX event report: > 1 in/hr over the forks 02:00-05:00 CDT"))})

    def frame_at(self, t: float) -> ObservationFrame:
        raining = self.rain_window is not None and self.rain_window[0] <= t <= self.rain_window[1]
        rain = {pid: (REPLAY_HEAVY_IN_HR if raining and pid in self.rain_points else 0.0) for pid in self.point_ids}
        return ObservationFrame(mode="replay", alerts=tuple(a for a in self.alerts if a.active_at(t)),
                                rain_in_hr=MappingProxyType(rain), sources=self.sources)
