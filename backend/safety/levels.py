"""Danger levels, ordered. Comparisons (>=, max) are meaningful."""

from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    NONE = 0
    WATCH = 1      # flooding possible: be ready
    WARNING = 2    # flooding likely near you: avoid low water, plan to move
    DANGER = 3     # water near you or ahead of you: are you safe?
    CRITICAL = 4   # water at you (or stopped in it): call, family, responders

    @property
    def label(self) -> str:
        return self.name.lower()

    def bump(self, steps: int = 1) -> "Level":
        """Raise by `steps`, capped at CRITICAL. NONE stays NONE: vulnerability never invents a hazard."""
        if self is Level.NONE:
            return self
        return Level(min(Level.CRITICAL, self + steps))

    @classmethod
    def parse(cls, value: str) -> "Level":
        try:
            return cls[value.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown level {value!r}; one of {[lv.label for lv in cls]}") from exc
