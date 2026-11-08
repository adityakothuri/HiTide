"""Check a mesh exported from Fusion (or any CAD tool) against the tabletop ground truth.

    cd backend && uv run python -m scripts.check_print_export ../data/print_model/kerrville_tabletop.stl

Fusion may add features (fillets on the rim, a logo on the base) but must not move or reshape the terrain:
the vision ground truth is truth.npz, and the print has to match it. Checks the footprint, the rim/pad top
height and the terrain heights sampled from the mesh against truth.npz.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

from sim.print_mesh import is_watertight, read_stl, volume_mm3
from vision.tabletop import MODEL_DIR

TOL_MM = 0.05
HEIGHT_TOL_MM = 0.20          # ~0.36 m world at 0.55 mm/m; the print budget itself is 0.1 mm
VOLUME_TOL = 0.02             # decimation/BRep conversion may change volume a little, not more


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare an exported tray mesh with truth.npz")
    ap.add_argument("mesh", type=Path)
    args = ap.parse_args()
    man = json.loads((MODEL_DIR / "manifest.json").read_text())
    t = np.load(MODEL_DIR / "truth.npz")
    tris = read_stl(args.mesh)
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    size = hi - lo
    tris = tris - [lo[0], lo[1], 0.0]           # Fusion may re-origin the body in x/y
    expect = np.array(man["size_mm"])
    checks = {
        "footprint_x": abs(size[0] - expect[0]) <= TOL_MM,
        "footprint_y": abs(size[1] - expect[1]) <= TOL_MM,
        "rim_top": abs(hi[2] - man["rim_top_mm"]) <= TOL_MM,
        "base_at_z0": abs(lo[2]) <= TOL_MM,
    }
    # every top-surface vertex of the mesh must sit on the CAD heightmap (bilinear); walls/bottom are at z = 0
    res = float(t["res_mm"])
    v = np.unique(tris.reshape(-1, 3).round(5), axis=0)
    top = v[v[:, 2] > TOL_MM]
    fi, fj = top[:, 1] / res, top[:, 0] / res
    truth_z = ndimage.map_coordinates(t["terrain_mm"].astype(float), [fi, fj], order=1, mode="nearest")
    err = top[:, 2] - truth_z
    p95 = float(np.percentile(np.abs(err), 95)) if len(err) else float("inf")
    checks["terrain_p95"] = p95 <= HEIGHT_TOL_MM
    checks["watertight"] = is_watertight(tris)
    vol = volume_mm3(tris) / 1000
    checks["volume"] = abs(vol - man["volume_cm3"]["terrain"]) <= VOLUME_TOL * man["volume_cm3"]["terrain"]
    print(f"{args.mesh.name}: {len(tris)} triangles")
    print(f"  size {size.round(3).tolist()} mm (expect {expect.round(3).tolist()}), "
          f"volume {vol:.1f} cm3 (truth terrain {man['volume_cm3']['terrain']:.1f})")
    print(f"  top-surface vertices vs CAD heightmap: |dz| p95 {p95:.3f} mm over {len(top)} vertices")
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
