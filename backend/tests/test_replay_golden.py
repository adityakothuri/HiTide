"""The July 4, 2025 replay is bit-for-bit what it was before the observation layer (per-minute p / status /
node states / counters / alerts). Slow (~15 min): RUN_SLOW=1 uv run pytest tests/test_replay_golden.py"""

import json
import os
from pathlib import Path

import pytest

from tests.golden_replay import replay_digest

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "replay_golden.json").read_text())


@pytest.mark.skipif(os.environ.get("RUN_SLOW") != "1", reason="slow full-replay regression; set RUN_SLOW=1")
@pytest.mark.parametrize("policy", ["priority", "patrol"])
def test_replay_unchanged(policy):
    assert replay_digest(policy) == GOLDEN[policy]
