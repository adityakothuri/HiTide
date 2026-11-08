"""Live Texas feeds as an observation provider for the Hill Country region (REGION_MODE=live).

Each source polls on its own cadence (config/regions/hill_country.yaml `live.poll_s`), keeps its last good data,
and is combined into a fresh ObservationFrame on every `frame_at(t)`. Correctness rules:
- A failed fetch never turns into "no warning / no rain / dry": the last good data stays, marked stale,
  and ages out by its OWN timestamps (alert end, rain product time, report time, gauge reading time).
- Missing evidence is None/absent, never zero.
- Retrieval time never stands in for observation time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping

from observe import http
from observe.alerts import Alert, parse_nws_alerts, region_alerts
from observe.frame import ObservationFrame, SourceStatus
from observe.gauges import Forecast, build_hydro, parse_nwps, usgs_series
from observe.rain import QpeGrid, decode_qpe_window, sample_points
from observe.reports import REPORT_MAX_AGE_S, lsr_closures
from sim.region_flood import RegionFlood

log = logging.getLogger(__name__)

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
USGS_SERIES_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"
MRMS_URL = "https://mrms.ncep.noaa.gov/2D/{product}/"
LSR_URL = "https://mesonet.agron.iastate.edu/geojson/lsr.geojson"
NWPS_URL = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}"
FORECAST_FLOOD = ("minor", "moderate", "major")
FORECAST_ALERT_HOLD_S = 6 * 3600.0
FORECAST_MAX_AGE_S = 24 * 3600.0
DETECTION_SOURCES = ("usgs_gage", "nws_alerts", "mrms", "lsr", "nwps")

# Statewide collectors (feeds/) that are deliberately NOT detection inputs for this region, and why.
NOT_USED = {
    "drivetexas_work_zones": "Construction work zones only (WZDx); flood closures need DriveTexas conditions access (401)",
    "lcra_hydromet": "Lower Colorado basin network; the Guadalupe at Kerr County is outside it",
    "sariver_crossings": "San Antonio basin (Bexar and south); outside the region, timestamps lack a timezone",
    "atx_flood_closures": "Austin-area jurisdictions only",
    "hcfcd_water_levels": "Harris County only",
    "hcfcd_inundation": "Harris County only; raster not georeferenced yet",
    "txdot_cameras": "No timestamped images available; no automated water detection",
    "transtar_incidents": "Houston only; live access pending",
    "noaa_flash": "Modeled runoff guidance; horizon/version unverified, not used as evidence",
    "usgs_flood_impacts": "Kerrville impact points are a bank, pool, parking lot, restaurant: not road crossings",
}

FetchJson = Callable[..., Awaitable[http.Fetched]]
FetchText = Callable[[str], Awaitable[str]]
FetchBytes = Callable[[str], Awaitable[bytes]]


def _iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


HISTORY_S = 7 * 86400.0


def _merge(old: list[tuple[str, float]], new: list[tuple[str, float]], now: float) -> list[tuple[str, float]]:
    """Recent readings over the stored history: same timestamp -> the newer fetch wins (USGS revises provisional
    data); older than 7 days is dropped."""
    by_t = {_epoch(t): (t, v) for t, v in old}
    by_t.update({_epoch(t): (t, v) for t, v in new})
    return [by_t[k] for k in sorted(k for k in by_t if k is not None and k >= now - HISTORY_S)]


def _is_feature_collection(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("features"), list)


@dataclass(frozen=True)
class _Src:
    status: SourceStatus
    data: Any = None


@dataclass
class LiveObservations:
    region: Any
    points: Mapping[str, dict]
    static_positions: Mapping[str, tuple[float, float]]
    celerity: float
    fetch_json: FetchJson = http.fetch_json
    fetch_text: FetchText = http.fetch_text
    fetch_bytes: FetchBytes = http.fetch_bytes
    decode_qpe: Callable[[bytes, Mapping], QpeGrid] = decode_qpe_window
    clock: Callable[[], float] = time.time
    mode: str = "live"
    _src: dict[str, _Src] = field(default_factory=dict)
    _series: dict[str, list] = field(default_factory=dict)
    _flood: RegionFlood | None = None
    _rev: int = 0
    _usgs_polls: int = 0
    _full_sites: set = field(default_factory=set)
    _flood_dirty: bool = False
    _tasks: list[asyncio.Task] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cfg = self.region.cfg["live"]
        self.bbox = self.region.cfg["bbox"]
        self.zones = frozenset(self.region.cfg.get("nws_zones", ()))
        self.gauges = list(self.region.cfg["gauges"])
        self._points_ll = {pid: (p["lon"], p["lat"]) for pid, p in self.points.items()}
        for name in DETECTION_SOURCES:
            self._src[name] = _Src(SourceStatus("pending", "none", detail="waiting for first poll"))

    # ---- lifecycle -------------------------------------------------------
    async def refresh_all(self) -> None:
        await asyncio.gather(*(self.refresh(n) for n in DETECTION_SOURCES))

    async def refresh(self, name: str) -> None:
        try:
            await getattr(self, f"_poll_{name}")()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # one source failing must never stop the others
            log.exception("live source %s failed", name)
            self._mark_failed(name, type(exc).__name__)

    async def start(self) -> None:
        await self.stop()
        await self.refresh_all()
        self._tasks = [asyncio.create_task(self._every(n, float(self.cfg["poll_s"][n]))) for n in DETECTION_SOURCES]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks = []

    async def _every(self, name: str, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            await self.refresh(name)

    def _now_iso(self) -> str:
        return _iso(self.clock()) or ""

    def _mark_failed(self, name: str, error: str) -> None:
        prev = self._src[name]
        had = prev.data is not None
        self._src[name] = replace(prev, status=SourceStatus("stale" if had else "unavailable", prev.status.provenance,
                                                            prev.status.as_of, self._now_iso(), prev.status.detail, error))

    def _ok(self, name: str, data: Any, provenance: str, as_of: str | None, detail: str,
            error: str | None = None) -> None:
        health = "ok" if provenance == "live" and not error else "stale"
        self._src[name] = _Src(SourceStatus(health, provenance, as_of, self._now_iso(), detail, error), data)

    # ---- sources ---------------------------------------------------------
    async def _poll_nws_alerts(self) -> None:
        got = await self.fetch_json("nws_alerts_tx", NWS_ALERTS_URL, {"area": "TX"}, 10.0)
        if not _is_feature_collection(got.data):   # a 200 with an error body is not "no warnings"
            return self._mark_failed("nws_alerts", got.error or "malformed_response")
        alerts = region_alerts(parse_nws_alerts(got.data), self.bbox, self.zones)
        newest = max((a.sent for a in alerts if a.sent), default=None)
        self._ok("nws_alerts", alerts, got.provenance, newest,
                 f"{len(alerts)} flood alert(s) touching the region", got.error)

    async def _poll_usgs_gage(self) -> None:
        sites = [g["site"] for g in self.gauges]
        refresh_all = self._usgs_polls % int(self.cfg["gauge_full_every"]) == 0
        self._usgs_polls += 1
        # A site without a successful 7-day fetch keeps asking for one: its baseline needs the full window.
        full = {s: refresh_all or s not in self._full_sites for s in sites}
        results = await asyncio.gather(*(self.fetch_json(
            f"usgs_{s}_{'full' if full[s] else 'recent'}", USGS_SERIES_URL,
            {"monitoring_location_id": f"USGS-{s}", "parameter_code": "00065",
             "time": self.cfg["gauge_window"] if full[s] else self.cfg["gauge_recent_window"], "limit": 3000,
             "f": "json"}, 15.0) for s in sites))
        failed, provenance = [], "live"
        for site, got in zip(sites, results):
            series = usgs_series(got.data) if got.data is not None else None
            if not series:
                failed.append(site)   # keep this site's previous series; it ages offline by reading time
                continue
            if got.provenance != "live":
                provenance = "cached"
            # Only a live full window replaces history; anything else (recent, or an older cached full) merges.
            replace_all = full[site] and got.provenance == "live"
            merged = series if replace_all else _merge(self._series.get(site, []), series, self.clock())
            if full[site] and got.provenance == "live":
                self._full_sites.add(site)
            if merged != self._series.get(site):
                self._series[site] = merged
                self._flood_dirty = True
        if not self._series:
            return self._mark_failed("usgs_gage", "no gauge data")
        if self._flood_dirty or self._flood is None:
            hydro = build_hydro(self._series, self.static_positions)
            self._flood = await asyncio.to_thread(
                RegionFlood, self.region, hydro, baseline="window_min", celerity=self.celerity,
                max_gap_s=float(self.cfg["gauge_max_gap_s"]))
            self._flood_dirty = False   # only after a successful build
            self._rev += 1
        newest = max(s[-1][0] for s in self._series.values() if s)
        self._ok("usgs_gage", self._rev, provenance, newest,
                 f"{len(sites) - len(failed)}/{len(sites)} gauges reporting",
                 f"no data: {','.join(failed)}" if failed else None)

    async def _poll_mrms(self) -> None:
        from feeds.noaa_products import newest_grib_reference

        product = self.cfg["rain_product"]
        url = MRMS_URL.format(product=product)
        ref = newest_grib_reference(await self.fetch_text(url), f"MRMS_{product}")
        if ref is None:
            return self._mark_failed("mrms", "missing_timestamped_grib")
        grid = await asyncio.to_thread(self.decode_qpe, await self.fetch_bytes(url + ref[0]), self.bbox)
        if abs(grid.valid_t - (_epoch(ref[1]) or grid.valid_t)) > 60:
            return self._mark_failed("mrms", "grib_time_mismatch")   # file name and GRIB tag disagree
        values = sample_points(grid, self._points_ll)
        peak = max((v for v in values.values() if v is not None), default=None)
        self._ok("mrms", (grid.valid_t, values), "live", _iso(grid.valid_t),
                 f"{product}: max {peak if peak is not None else 'n/a'} in/1 h at critical points")

    async def _poll_lsr(self) -> None:
        end = datetime.fromtimestamp(self.clock(), tz=timezone.utc)
        start = end - timedelta(seconds=REPORT_MAX_AGE_S)
        params = {"states": "TX", "sts": start.strftime("%Y-%m-%dT%H:%MZ"), "ets": end.strftime("%Y-%m-%dT%H:%MZ")}
        got = await self.fetch_json("lsr_tx", LSR_URL, params, 10.0)
        if not _is_feature_collection(got.data) or got.provenance == "cached":  # a cached window is another window
            return self._mark_failed("lsr", got.error or "malformed_response")
        feats = got.data["features"]
        times = [p.get("valid") for f in feats if isinstance(f, dict) for p in [f.get("properties") or {}]
                 if isinstance(p, dict) and isinstance(p.get("valid"), str)]
        self._ok("lsr", got.data, got.provenance, max(times, default=None),
                 f"{len(feats)} Texas storm report(s) in the last 3 h (checked through {end.isoformat()})")

    async def _poll_nwps(self) -> None:
        prev = {f.lid: f for f in (self._src["nwps"].data or ())}
        out: list[Forecast] = []
        errors, provenance = [], "live"
        for g in self.gauges:
            lid = g.get("nws_lid")
            if not lid:
                continue
            gauge, fcst = await asyncio.gather(self.fetch_json(f"nwps_{lid}", NWPS_URL.format(lid=lid), None, 15.0),
                                               self.fetch_json(f"nwps_{lid}_fcst", NWPS_URL.format(lid=lid)
                                                               + "/stageflow/forecast", None, 15.0))
            if not isinstance(gauge.data, dict) or not isinstance(fcst.data, dict):
                errors.append(lid)        # a failed forecast fetch is not "no forecast": keep the last one
                if lid in prev:
                    out.append(prev[lid])
                continue
            if "cached" in (gauge.provenance, fcst.provenance):
                provenance = "cached"
            out.append(parse_nwps(gauge.data, fcst.data, site=g["site"]))
        if not out:
            return self._mark_failed("nwps", f"no data: {','.join(errors)}")
        self._ok("nwps", tuple(out), provenance, max((f.issued_at or "" for f in out), default=None) or None,
                 "; ".join(f"{f.lid} crest {f.crest_ft} ft ({f.crest_category})" for f in out),
                 f"no data: {','.join(errors)}" if errors else None)

    # ---- frame -------------------------------------------------------------
    def _rain(self, t: float) -> dict[str, float | None]:
        data = self._src["mrms"].data
        if data is None or t - data[0] > float(self.cfg["rain_max_age_s"]):
            return {pid: None for pid in self.points}   # too old: no evidence (not "dry")
        return dict(data[1])

    def _forecast_alerts(self, forecasts: tuple[Forecast, ...]) -> tuple[Alert, ...]:
        out = []
        for f in forecasts:
            crest_t, issued_t = _epoch(f.crest_at), _epoch(f.issued_at)
            if f.crest_category not in FORECAST_FLOOD or crest_t is None:
                continue
            if issued_t is None or self.clock() - issued_t > FORECAST_MAX_AGE_S:
                continue   # an old forecast is not a current flood forecast
            issued = _epoch(f.issued_at) or crest_t - FORECAST_ALERT_HOLD_S
            out.append(Alert(id=f"nwps-{f.lid}-{f.issued_at}", event=f"River forecast: {f.crest_category} flooding",
                             level="forecast", headline=f"NWS forecasts {f.name} to crest at {f.crest_ft:g} ft "
                             f"({f.crest_category} flood stage) at {f.crest_at}", effective=issued,
                             expires=crest_t + FORECAST_ALERT_HOLD_S, source="nwps", sent=f.issued_at, area=f.name))
        return tuple(out)

    def _aged(self, name: str, t: float) -> SourceStatus:
        """Health from the age of the data actually in use, evaluated now (not at the last poll)."""
        st = self._src[name].status
        if st.status != "ok":
            return st
        if name == "mrms" and t - (_epoch(st.as_of) or 0.0) > float(self.cfg["rain_max_age_s"]):
            return replace(st, status="stale", error="rain product too old; treated as no evidence")
        if name == "usgs_gage" and self._flood is not None and not any(
                g["online"] for g in self._flood.gauge_status(t)):
            return replace(st, status="stale", error="no gauge has reported within the offline window")
        return st

    def sources(self) -> dict[str, SourceStatus]:
        t = self.clock()
        out = {k: self._aged(k, t) for k in self._src}
        out.update({k: SourceStatus("not_used", "none", detail=why) for k, why in NOT_USED.items()})
        return out

    def frame_at(self, t: float) -> ObservationFrame:
        alerts = self._src["nws_alerts"].data or ()
        forecasts = self._src["nwps"].data or ()
        lsr = self._src["lsr"].data
        closures = lsr_closures(lsr, self.points, t) if lsr is not None else {}
        return ObservationFrame(mode="live", hydro_rev=self._rev, flood=self._flood,
                                alerts=tuple(alerts) + self._forecast_alerts(forecasts),
                                rain_in_hr=MappingProxyType(self._rain(t)), closures=MappingProxyType(closures),
                                forecasts=tuple(forecasts), sources=MappingProxyType(self.sources()))
