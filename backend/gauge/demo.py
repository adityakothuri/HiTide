"""Offline demo: render a synthetic tray frame, read the water level, write an overlay PNG.

    cd backend && ~/tello-env/Scripts/python.exe -m gauge.demo --level-ft 3 --elevation 50 --out demo.png
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from .camera import tello_default
from .model import level_mm, load_tray
from .synth import Noise, look_at_pose, render
from .water import GaugeReader

logger = logging.getLogger(__name__)

DEFAULT_OUT = "gauge_demo.png"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gauge.demo", description=__doc__.splitlines()[0])
    parser.add_argument("--level-ft", type=float, default=3.0, help="true flood level to render (ft)")
    parser.add_argument("--elevation", type=float, default=50.0, help="camera elevation above the tray (deg)")
    parser.add_argument("--azimuth", type=float, default=30.0, help="camera azimuth around the tray (deg)")
    parser.add_argument("--distance", type=float, default=380.0, help="camera distance (mm)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="overlay PNG path")
    parser.add_argument("--tray", default=None, help="tray directory (default data/gauge_tray_160)")
    parser.add_argument("--dye", default="blue", choices=("blue", "green", "red"))
    parser.add_argument("--no-baseline", action="store_true", help="read from dye colour only")
    parser.add_argument("--seed", type=int, default=0)
    return parser


def run(args: argparse.Namespace) -> dict:
    model = load_tray(args.tray)
    cam = tello_default()
    rng = np.random.default_rng(args.seed)
    pose = look_at_pose(model, args.distance, args.elevation, args.azimuth)
    noise = Noise.modest()
    reader = GaugeReader(model, cam, dye=args.dye)
    if not args.no_baseline:
        ok, reason = reader.set_baseline(render(model, cam, pose, None, noise=noise, rng=rng))
        if not ok:
            logger.warning("baseline not captured: %s", reason)
    frame = render(model, cam, pose, level_mm(model, args.level_ft), noise=noise, rng=rng)
    estimate = replace(reader.read(frame), simulated=True)
    out_path = Path(args.out)
    if not cv2.imwrite(str(out_path), reader.overlay(frame, estimate)):
        raise OSError(f"could not write overlay to {out_path}")
    return estimate.to_dict()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except (OSError, ValueError) as exc:
        print(f"gauge.demo failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
