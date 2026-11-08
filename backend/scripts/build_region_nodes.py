"""Precompute floodable critical points + population nodes:  uv run python -m scripts.build_region_nodes"""

from __future__ import annotations

import json
import sys
import time

from app.config import DATA_DIR
from population.nodes import build_nodes
from sim.region import load_region


def main(region_id: str = "hill_country") -> int:
    t0 = time.time()
    out = build_nodes(load_region(region_id))
    path = DATA_DIR / "region" / region_id / "nodes.json"
    path.write_text(json.dumps(out))
    print(f"floodable={out['all_floodable']} used_points={len(out['points'])} nodes={len(out['nodes'])} "
          f"safe_nodes={len(out['safe_nodes'])} households={out['households_total']} exposed={out['households_exposed']} "
          f"in {time.time() - t0:.0f}s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
