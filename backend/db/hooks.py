"""Small adapters that persist runtime state without rewriting the code that mutates it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class PersistedDict(dict):
    """A dict that reports every assignment (e.g. World.cases): `on_set(key, value)` runs after the write.
    The callback must not block (it should enqueue a write-behind job)."""

    def __init__(self, on_set: Callable[[Any, Any], None], *args: Any, **kw: Any):
        super().__init__(*args, **kw)
        self._on_set = on_set

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._on_set(key, value)
