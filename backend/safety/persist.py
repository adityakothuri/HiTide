"""Safety monitor <-> primary database (SpacetimeDB): positions, outreach ladders, and the public danger table.

Only rows that changed are written, through the write-behind queue (never blocking a refresh).
Rows carry the mode they were made in; only live-mode state is restored after a restart (a replay always
starts from its own beginning, so its ladders are cleared instead).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from safety.levels import Level
from safety.motion import MotionState
from safety.policy import response_from_dict, response_to_dict

if TYPE_CHECKING:
    from safety.danger import DangerAssessment
    from safety.monitor import UserTrack
    from safety.users import SafetyUser

log = logging.getLogger(__name__)


def danger_row(u: "SafetyUser", a: "DangerAssessment", mode: str) -> dict[str, Any]:
    """Public row: a real user's (rounded) position only while they are at DANGER or worse."""
    # danger_latest is a public table: real people get ~1 km precision even at danger (responders use the API).
    show = u.simulated or a.level >= Level.DANGER
    digits = 5 if u.simulated else 2
    return {"user_id": u.id, "level": a.level.label, "hazard_level": a.hazard_level.label,
            "top_reason": a.reasons[0] if a.reasons else "", "advice": a.advice, "confidence": a.confidence,
            "lat": round(a.motion.lat, digits) if show else None, "lon": round(a.motion.lon, digits) if show else None,
            "band": a.vulnerability.band, "mode": mode, "assessed_at": a.assessed_at}


class SafetyPersistence:
    def __init__(self, db: Any, edge_ids: tuple[str, ...], edge_index: dict[str, int]):
        self.db, self.edge_ids, self.edge_index = db, edge_ids, edge_index
        self._saved_resp: dict[str, str] = {}
        self._saved_track: dict[str, str] = {}

    # ---- writes ---------------------------------------------------------------
    def save(self, tracks: dict[str, "UserTrack"], touched: set[str], dangers: list[dict[str, Any]], mode: str) -> None:
        responses, positions = [], []
        for uid in touched:
            t = tracks.get(uid)
            if t is None:
                continue
            state = {**response_to_dict(t.response), "mode": mode}
            blob = json.dumps(state, sort_keys=True)
            if self._saved_resp.get(uid) != blob:
                self._saved_resp[uid] = blob
                responses.append({"user_id": uid, "episode_level": t.response.episode_level.label, "state": state})
            if t.pinged and t.motion is not None:
                track = {"user_id": uid, "motion": {**t.motion.__dict__, "mode": mode},
                         "route": [self.edge_ids[e] for e in t.route_edges], "pinged": True}
                tblob = json.dumps(track, sort_keys=True)
                if self._saved_track.get(uid) != tblob:
                    self._saved_track[uid] = tblob
                    positions.append(track)
        data, writer = self.db.data, self.db.writer
        if dangers:
            writer.submit(lambda: data.save_dangers(dangers))
        if responses:   # on failure forget we "saved" them, so the next refresh writes them again
            uids = [r["user_id"] for r in responses]
            writer.submit(lambda: data.save_responses(responses), on_fail=lambda: self._forget(self._saved_resp, uids))
        if positions:
            uids_t = [r["user_id"] for r in positions]
            writer.submit(lambda: data.save_tracks(positions), on_fail=lambda: self._forget(self._saved_track, uids_t))

    @staticmethod
    def _forget(cache: dict[str, str], uids: list[str]) -> None:
        for uid in uids:
            cache.pop(uid, None)

    def wipe(self) -> None:
        self._saved_resp.clear()
        self._saved_track.clear()
        data = self.db.data
        self.db.writer.submit(lambda: data.wipe_runtime("safety"))

    # ---- restore (live mode only) --------------------------------------------------
    def restore(self) -> dict[str, tuple[MotionState | None, bool, tuple[int, ...], Any]]:
        """uid -> (motion, pinged, route_edges, ResponseState) for state saved in live mode."""
        try:
            tracks = self.db.data.load_tracks()
            responses = self.db.data.load_responses()
        except Exception as exc:  # restore is best effort: a cold start only means ladders start over
            log.error("could not restore safety state (%s); starting fresh", type(exc).__name__)
            return {}
        out: dict[str, tuple[MotionState | None, bool, tuple[int, ...], Any]] = {}
        for uid in set(tracks) | set(responses):
            tr, rs = tracks.get(uid), responses.get(uid)
            motion, route, pinged = None, (), False
            if tr and isinstance(tr.get("motion"), dict) and tr["motion"].get("mode") == "live":
                fields = {k: v for k, v in tr["motion"].items() if k != "mode"}
                try:
                    motion = MotionState(**fields)
                    pinged = bool(tr.get("pinged"))
                    route = tuple(self.edge_index[e] for e in tr.get("route", []) if e in self.edge_index)
                except TypeError:
                    motion = None
            resp = response_from_dict(rs) if rs and rs.get("mode") == "live" else None
            if motion is not None or resp is not None:
                out[uid] = (motion, pinged, route, resp)
        log.info("restored live safety state for %d users", len(out))
        return out
