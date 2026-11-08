"""Simulation engine: owns sim clock + flood state and emits WS events on each tick.

Stages (pretrip / enroute / stopped) plug in via `on_tick` hooks registered later.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import numpy as np

from app.config import settings
from scoring.road_status import classify
from sim.drivers import Driver
from sim.flood import FloodParams, depth_in, river_wse, wse_at
from sim.town import Town

log = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
TickHook = Callable[["Engine"], Awaitable[None]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class FloodState:
    active: bool = False
    t_flood_s: float = 0.0          # sim seconds since the flood began
    river_wse_m: float = 0.0


@dataclass
class Engine:
    town: Town
    drivers: list[Driver]
    emit: Emit
    speed: float = 60.0
    t_sim_s: float = 0.0
    flood: FloodState = field(default_factory=FloodState)
    alert: dict[str, Any] | None = None
    depths: np.ndarray = field(init=False)
    statuses: dict[str, str] = field(default_factory=dict)  # only non-open
    hooks: list[TickHook] = field(default_factory=list)
    last_dt: float = 0.0
    _task: asyncio.Task | None = None

    def __post_init__(self) -> None:
        self.params = FloodParams(**settings()["flood"])
        self.flood = replace(self.flood, river_wse_m=self.params.base_wse_m)
        self.depths = np.zeros(len(self.town.edge_ids))

    # ---- control -------------------------------------------------------
    def start(self) -> None:
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def begin_flood(self, alert: dict[str, Any]) -> None:
        self.flood = replace(self.flood, active=True, t_flood_s=0.0)
        self.alert = alert
        await self.emit("alert", alert)

    def reset(self) -> None:
        self.t_sim_s = 0.0
        self.flood = FloodState(river_wse_m=self.params.base_wse_m)
        self.alert = None
        self.depths = np.zeros(len(self.town.edge_ids))
        self.statuses = {}

    # ---- queries -------------------------------------------------------
    def depth_of(self, edge_id: str) -> float:
        idx = self.town.edge_index.get(edge_id)
        return 0.0 if idx is None else float(self.depths[idx])

    def status_of(self, edge_id: str) -> str:
        return self.statuses.get(edge_id, "open")

    def closed_edges(self) -> set[str]:
        return {e for e, s in self.statuses.items() if s in ("closed", "float", "boat")}

    def segment_states(self) -> list[dict[str, Any]]:
        return [{"edge_id": e, "depth_in": round(self.depth_of(e), 1), "status": s} for e, s in self.statuses.items()]

    # ---- tick ----------------------------------------------------------
    async def _run(self) -> None:
        tick = float(settings()["clock"]["tick_real_s"])
        while True:
            try:
                await self.step(tick * self.speed)
            except Exception:  # noqa: BLE001 - keep the sim alive, log the failure
                log.exception("engine tick failed")
            await asyncio.sleep(tick)

    async def step(self, dt_sim_s: float) -> None:
        self.last_dt = dt_sim_s
        self.t_sim_s += dt_sim_s
        if self.flood.active:
            await self._advance_flood(dt_sim_s)
        for hook in self.hooks:
            try:
                await hook(self)
            except Exception:  # noqa: BLE001 - one broken stage must not stop the others
                log.exception("tick hook %s failed", getattr(hook, "__name__", hook))

    async def _advance_flood(self, dt_sim_s: float) -> None:
        t_flood = self.flood.t_flood_s + dt_sim_s
        wse0 = river_wse(t_flood, self.params)
        self.flood = replace(self.flood, t_flood_s=t_flood, river_wse_m=wse0)
        self.depths = depth_in(wse_at(self.town.river_dist_m, wse0, self.params), self.town.elev_m)
        changed = self._update_statuses()
        if changed:
            await self.emit("segments.update", {
                "t_sim_s": round(self.t_sim_s, 1), "river_wse_m": round(wse0, 2), "segments": changed,
            })

    def _update_statuses(self) -> list[dict[str, Any]]:
        changed = []
        wet = np.nonzero(self.depths > 0)[0]
        seen = set()
        for idx in wet:
            eid = self.town.edge_ids[idx]
            status = classify(float(self.depths[idx])).value
            seen.add(eid)
            if status == "open":
                if self.statuses.pop(eid, None):
                    changed.append({"edge_id": eid, "depth_in": round(float(self.depths[idx]), 1), "status": "open"})
                continue
            if self.statuses.get(eid) != status:
                self.statuses[eid] = status
                changed.append({"edge_id": eid, "depth_in": round(float(self.depths[idx]), 1), "status": status})
        for eid in [e for e in self.statuses if e not in seen]:
            self.statuses.pop(eid)
            changed.append({"edge_id": eid, "depth_in": 0.0, "status": "open"})
        return changed
