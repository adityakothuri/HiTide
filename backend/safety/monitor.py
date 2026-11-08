"""SafetyMonitor: every loop step and every location ping -> re-assess users -> ladder -> outreach.

Threading: `refresh`/`ping`/`reply` mutate per-user state under one lock and are cheap enough to call from a
worker thread (assessment is ~1 ms/user). Outreach sends are async and run on the event loop (`dispatch`).
Clock: replay uses the loop's sim time for everything (timers, pings); live uses wall-clock time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Mapping

from app.config import safety_settings
from outreach import voice_elevenlabs
from outreach.allowlist import normalize_phone, resolve_phone
from outreach.base import OutboundMessage
from outreach.call_summary import classify_call
from safety.context import SafetyContext, build_context, empty_context
from safety.danger import DangerAssessment, assess_user
from safety.hazard import Locator
from safety.levels import Level
from safety.messages import render
from safety.motion import MotionState, Ping, at_rest, update
from safety.policy import Action, ResponseState, apply_call_result, apply_reply, decide
from safety.users import STATE_PATH, SafetyUser, UserRegistry, atomic_write_json

log = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
POLL_OPTIONS = ("I'm safe", "I need help")
CALL_POLL_S, CALL_WATCH_MAX_S = 3.0, 180.0
PERSIST_EVERY_S = 10.0


@dataclass
class UserTrack:
    motion: MotionState | None = None
    pinged: bool = False
    route_edges: tuple[int, ...] = ()
    response: ResponseState = field(default_factory=ResponseState)
    last: DangerAssessment | None = None


@dataclass(frozen=True)
class Decision:
    user: SafetyUser
    assessment: DangerAssessment
    actions: tuple[Action, ...]
    changed: bool


class SafetyMonitor:
    def __init__(self, locator: Locator, users: UserRegistry, outreach: Any, emit: Emit,
                 cfg: Mapping[str, Any] | None = None, state_path: Any = STATE_PATH, clock: Callable[[], float] = time.time):
        self.loc, self.users, self.outreach, self.emit = locator, users, outreach, emit
        self.cfg: Mapping[str, Any] = cfg if cfg is not None else safety_settings()
        self.scale = float(self.cfg["ladder"]["demo_time_scale"]) if os.environ.get("SAFETY_DEMO") == "1" else 1.0
        self.lock = threading.RLock()
        self.tracks: dict[str, UserTrack] = {}
        self.ctx: SafetyContext = empty_context(len(locator.region.edge_ids))
        self.state_path = state_path
        self.clock = clock
        self._last_persist = 0.0
        self._background: set[asyncio.Task] = set()
        self._load_positions()

    # ---- clock -------------------------------------------------------------
    def now(self) -> float:
        if self.ctx.mode == "replay" and self.ctx.t is not None:
            return self.ctx.t
        return self.clock()

    # ---- state ---------------------------------------------------------------
    def reset(self, mode: str = "replay") -> None:
        """New scenario / mode switch: forget assessments and ladders; keep enrolled users and pinged positions in live."""
        with self.lock:
            keep = {uid: UserTrack(t.motion, t.pinged, t.route_edges) for uid, t in self.tracks.items()
                    if t.pinged and mode == "live"}
            self.tracks = keep
            self.ctx = empty_context(len(self.loc.region.edge_ids), mode)
        for task in list(self._background):
            task.cancel()

    def _track(self, uid: str) -> UserTrack:
        return self.tracks.setdefault(uid, UserTrack())

    def is_moving(self, uid: str) -> bool:
        t = self.tracks.get(uid)
        return bool(t and t.motion and t.motion.state == "driving")

    # ---- assessment ------------------------------------------------------------
    def _motion_of(self, u: SafetyUser, t: UserTrack, now: float) -> MotionState:
        return t.motion if t.motion is not None else at_rest(u.home_lat, u.home_lon, now)

    def _assess(self, u: SafetyUser, t: UserTrack, now: float) -> Decision:
        a = assess_user(self.loc, self.ctx, u.id, u.profile, u.age, self._motion_of(u, t, now), now,
                        t.route_edges, t.pinged, self.cfg)
        prev = t.last
        changed = prev is None or prev.level != a.level or prev.reasons[:1] != a.reasons[:1]
        resp, acts = decide(t.response, a, now, self.cfg, self.scale)
        t.response, t.last = resp, a
        return Decision(u, a, tuple(acts), changed)

    def refresh(self, ctx: SafetyContext | None = None) -> list[Decision]:
        """Re-assess every consented user against the newest loop belief. Call from a worker thread."""
        with self.lock:
            if ctx is not None:
                rewound = ctx.t is not None and self.ctx.t is not None and ctx.t < self.ctx.t - 1.0
                if rewound:   # the replay restarted: ladders and replay-clock positions belong to the old run
                    self.tracks = {}
                self.ctx = ctx
            if not self.ctx.ready:
                return []
            now = self.now()
            out = [self._assess(u, self._track(u.id), now) for u in self.users.all() if u.consented]
            self._maybe_persist(now)
            return out

    def ping(self, uid: str, p: Ping) -> Decision:
        """Fold a location ping in and re-assess that user now. Raises KeyError for unknown users."""
        u = self.users.get(uid)
        if u is None:
            raise KeyError(uid)
        with self.lock:
            now = self.now()
            if self.ctx.mode == "replay":   # the replay clock is the only clock: stamp pings with sim time
                last = self.tracks.get(uid)
                ts = now if not last or not last.motion else max(now, last.motion.ts + 1.0)
                p = replace(p, ts=ts)
            t = self._track(uid)
            t.motion, t.pinged = update(t.motion, p, self.cfg["motion"]), True
            d = self._assess(u, t, max(now, t.motion.ts))
            self._maybe_persist(now, force=True)
            return d

    def set_route(self, uid: str, coords: list[tuple[float, float]]) -> tuple[str, ...]:
        if self.users.get(uid) is None:
            raise KeyError(uid)
        edges = self.loc.snap_route(coords)
        with self.lock:
            self._track(uid).route_edges = edges
        return tuple(self.loc.region.edge_ids[e] for e in edges)

    def assessment(self, uid: str) -> DangerAssessment | None:
        u = self.users.get(uid)
        if u is None:
            return None
        with self.lock:
            t = self._track(uid)
            if t.last is None and self.ctx.ready:
                self._assess(u, t, self.now())   # first look: no outreach is sent from a GET
                t.response = ResponseState()
            return t.last

    def response(self, uid: str) -> ResponseState | None:
        t = self.tracks.get(uid)
        return t.response if t else None

    def at_risk(self, min_level: Level) -> list[DangerAssessment]:
        with self.lock:
            rows = [t.last for t in self.tracks.values() if t.last is not None and t.last.level >= min_level]
        return sorted(rows, key=lambda a: (-a.level, -a.vulnerability.score, a.user_id))

    def counts(self) -> dict[str, int]:
        with self.lock:
            out = {lv.label: 0 for lv in Level}
            for t in self.tracks.values():
                if t.last is not None:
                    out[t.last.level.label] += 1
            return out

    # ---- replies ------------------------------------------------------------------
    def find_by_phone(self, sender: str) -> tuple[SafetyUser, str] | None:
        """Sender (any format) -> (user, who). Matches drivers, emergency contacts and parents; newest episode wins."""
        want = normalize_phone(sender)
        if not want:
            return None
        best: tuple[float, SafetyUser, str] | None = None
        for u in self.users.all():
            for raw, by in self.users.phones_of(u):
                if normalize_phone(resolve_phone(raw, enrolled=not u.simulated) or "") != want:
                    continue
                t = self.tracks.get(u.id)
                seen = max(t.response.sent_at.values(), default=-1.0) if t else -1.0
                if best is None or seen > best[0]:
                    best = (seen, u, by)
        return (best[1], best[2]) if best else None

    def reply(self, uid: str, kind: str, by: str) -> list[Action]:
        with self.lock:
            t = self._track(uid)
            t.response, acts = apply_reply(t.response, kind, self.now(), by, t.last, self.cfg, self.scale)
            return acts

    def call_result(self, uid: str, answered: bool, reply: str | None, by: str) -> list[Action]:
        with self.lock:
            t = self._track(uid)
            t.response, acts = apply_call_result(t.response, answered, reply, self.now(), by, t.last, self.cfg, self.scale)
            return acts

    # ---- outreach ------------------------------------------------------------------
    def _phone_for(self, u: SafetyUser, recipient: str) -> str | None:
        return {"driver": u.phone, "emergency_contact": u.contact_phone, "parent": u.parent_phone}.get(recipient)

    async def dispatch(self, decisions: list[Decision]) -> None:
        for d in decisions:
            if d.changed:
                await self._emit("user.danger", {"user": d.user.public(), **d.assessment.public()})
            for act in d.actions:
                await self.execute(d.user, d.assessment, act)

    async def execute(self, u: SafetyUser, a: DangerAssessment | None, act: Action) -> None:
        if act.kind == "flag_responders":
            await self._emit("user.responders", {"user_id": u.id, "level": act.level.label,
                                                 "reasons": list(a.reasons) if a else [],
                                                 "location": a.motion.public() if a else None})
            return
        if act.kind == "open_case":
            await self._emit("user.case", {"user_id": u.id, "level": act.level.label,
                                           "reasons": list(a.reasons) if a else []})
            return
        phone = self._phone_for(u, act.recipient)
        if not phone:
            log.info("no %s phone for %s; %s skipped", act.recipient, u.id, act.template)
            return
        lang = a.vulnerability.language if a else "en"
        body, variables = render(act.template, a, u.name, lang)
        msg = OutboundMessage(driver_id=u.id, recipient=act.recipient, channel=act.kind, body=body, phone=phone,
                              case_id=f"safety-{u.id}", poll_options=POLL_OPTIONS if act.kind == "poll" else (),
                              variables=variables, enrolled=not u.simulated and u.consented)
        try:
            res = await self.outreach.send(msg)
        except Exception:  # outreach must never stop monitoring
            log.exception("safety outreach %s to %s failed", act.template, u.id)
            return
        call_id = res.get("call_id") if isinstance(res, dict) else None
        if act.kind == "voice" and call_id:
            self._spawn(self._watch_call(u.id, act.recipient, call_id))
        elif act.kind == "voice" and isinstance(res, dict) and res.get("status") in ("failed", "suppressed"):
            await self.dispatch_actions(u, self.call_result(u.id, False, None, act.recipient))

    async def dispatch_actions(self, u: SafetyUser, acts: list[Action]) -> None:
        a = self.tracks[u.id].last if u.id in self.tracks else None
        for act in acts:
            await self.execute(u, a, act)

    async def _watch_call(self, uid: str, by: str, call_id: str) -> None:
        try:
            deadline = time.monotonic() + CALL_WATCH_MAX_S
            conv = None
            while time.monotonic() < deadline:
                c = await voice_elevenlabs.get_conversation(call_id)
                if c and c.get("status") in ("done", "failed"):
                    conv = c
                    break
                await asyncio.sleep(CALL_POLL_S)
            outcome = classify_call(conv or {})
            u = self.users.get(uid)
            if u is None:
                return
            await self._emit("user.call", {"user_id": uid, "recipient": by, "answered": outcome.answered,
                                           "reply": outcome.reply, "summary": outcome.summary})
            await self.dispatch_actions(u, self.call_result(uid, outcome.answered, outcome.reply, by))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("safety call watcher failed for %s", uid)

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _emit(self, typ: str, payload: dict[str, Any]) -> None:
        try:
            await self.emit(typ, payload)
        except Exception:
            log.exception("safety emit %s failed", typ)

    # ---- loop hook --------------------------------------------------------------------
    async def after_step(self, loop: Any) -> None:
        """Called after every Hill Country loop step (replay or live)."""
        ctx = await asyncio.to_thread(build_context, loop)
        decisions = await asyncio.to_thread(self.refresh, ctx)
        await self.dispatch(decisions)

    # ---- persistence ---------------------------------------------------------------------
    def _maybe_persist(self, now: float, force: bool = False) -> None:
        if self.state_path is None or self.ctx.mode != "live":   # replay positions live on the sim clock
            return
        wall = time.monotonic()
        if not force and wall - self._last_persist < PERSIST_EVERY_S:
            return
        self._last_persist = wall
        rows = {uid: {"motion": t.motion.__dict__, "route": [self.loc.region.edge_ids[e] for e in t.route_edges]}
                for uid, t in self.tracks.items() if t.pinged and t.motion is not None}
        try:
            atomic_write_json(self.state_path, rows)
        except OSError:
            log.exception("could not persist safety positions")

    def _load_positions(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            rows = json.loads(self.state_path.read_text())
            idx = self.loc.region.edge_index
            for uid, r in rows.items():
                if self.users.get(uid) is None:
                    continue
                self.tracks[uid] = UserTrack(MotionState(**r["motion"]), True,
                                             tuple(idx[e] for e in r.get("route", []) if e in idx))
        except (OSError, ValueError, TypeError, KeyError):
            log.exception("could not load %s; starting without saved positions", self.state_path)
