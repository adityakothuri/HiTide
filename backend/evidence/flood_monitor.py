"""Provider-independent, in-memory demonstration of warning-backed events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class AcceptedFloodWarning:
    """Narrow projection of a single accepted observation revision."""

    observation_id: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if not self.observation_id or any(
            t.utcoffset() is None for t in (self.valid_from, self.valid_until)
        ):
            raise ValueError(
                "An observation ID and timezone-aware validity times are required"
            )
        if self.valid_from >= self.valid_until:
            raise ValueError("Warning validity interval must have positive duration")


@dataclass(frozen=True)
class EventTransition:
    event_id: str
    state: Literal["warning_active", "warning_expired"]
    evaluated_at: datetime
    supporting_observation_ids: tuple[str, ...]


class DemoFloodMonitor:
    """One event per original warning; state exists only for this process."""

    def __init__(self) -> None:
        self.warnings: dict[str, AcceptedFloodWarning] = {}
        self.active: set[str] = set()
        self.last_evaluation: datetime | None = None

    def evaluate(
        self, accepted: Iterable[AcceptedFloodWarning], *, as_of: datetime
    ) -> list[EventTransition]:
        if as_of.utcoffset() is None or (
            self.last_evaluation and as_of < self.last_evaluation
        ):
            raise ValueError("Evaluation time must be timezone-aware and nondecreasing")
        transitions = []
        for warning in accepted:
            self.warnings[warning.observation_id] = warning
        for obs_id, warning in list(self.warnings.items()):
            if as_of >= warning.valid_until:
                del self.warnings[obs_id]
                if obs_id in self.active:
                    self.active.remove(obs_id)
                    transitions.append(
                        EventTransition(
                            f"demo-event:{obs_id}", "warning_expired", as_of, (obs_id,)
                        )
                    )
            elif warning.valid_from <= as_of and obs_id not in self.active:
                self.active.add(obs_id)
                transitions.append(
                    EventTransition(
                        f"demo-event:{obs_id}", "warning_active", as_of, (obs_id,)
                    )
                )
        self.last_evaluation = as_of
        return transitions
