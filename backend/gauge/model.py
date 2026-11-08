"""Gauge tray model: the printed heightfield, landmarks and the ft <-> mm level mapping."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

logger = logging.getLogger(__name__)

TRAY_DIR_ENV = "GAUGE_TRAY_DIR"
DEFAULT_TRAY_NAME = "gauge_tray_160"
MANIFEST_FILE = "manifest.json"
TRUTH_FILE = "truth.npz"
MM_DIMENSIONS = 3


class _Record:
    """Mixin giving frozen records attribute and item access (``car.roof_mm`` or ``car["roof_mm"]``)."""

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


@dataclass(frozen=True)
class GaugeLevel(_Record):
    """One row of the pour table."""

    ft: int
    level_mm: float
    ml: float
    wet_fraction: float


@dataclass(frozen=True)
class Road(_Record):
    y_mm: float
    width_mm: float
    deck_mm: float
    crossing_x_mm: float


@dataclass(frozen=True)
class Car(_Record):
    centre_mm: tuple[float, float]
    road_mm: float
    body_top_mm: float
    roof_mm: float


@dataclass(frozen=True)
class House(_Record):
    centre_mm: tuple[float, float]
    ground_mm: float
    eave_mm: float
    ridge_mm: float


@dataclass(frozen=True, eq=False)
class TrayModel:
    """Everything the reader knows about the printed tray (all lengths in mm, z up)."""

    directory: Path
    name: str
    res_mm: float
    height_mm: np.ndarray  # [iy, ix] at x = ix * res_mm, y = iy * res_mm
    river: np.ndarray
    size_mm: tuple[float, float, float]
    floor_mm: float
    pool_mm: float
    step_mm: float
    rim_top_mm: float
    levels: tuple[GaugeLevel, ...]
    tag_corners_mm: dict[int, np.ndarray]  # id -> (4, 3), order TL, TR, BR, BL
    tag_dictionary: str
    tag_mm: float
    road: Road
    car: Car
    houses: tuple[House, ...]
    pad_mm: float = 0.0
    tag_centres_mm: dict[int, np.ndarray] | None = None


def default_tray_dir() -> Path:
    """Directory from ``GAUGE_TRAY_DIR``, else the repo's 160 mm build, else ``tray/`` beside the package
    (the standalone drone demo build)."""
    env = os.environ.get(TRAY_DIR_ENV)
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    repo = here.parents[2] / "data" / DEFAULT_TRAY_NAME
    return repo if repo.is_dir() else here.parents[1] / "tray"


def _readonly(array: np.ndarray) -> np.ndarray:
    out = np.array(array, copy=True)
    out.setflags(write=False)
    return out


def _build_tags(manifest: Mapping[str, Any]) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    corners: dict[int, np.ndarray] = {}
    centres: dict[int, np.ndarray] = {}
    for tag in manifest["fiducials"]["tags"]:
        tag_id = int(tag["id"])
        corners[tag_id] = _readonly(np.asarray(tag["corners_mm"], dtype=np.float64).reshape(4, 3))
        centres[tag_id] = _readonly(np.asarray(tag["centre_mm"], dtype=np.float64).reshape(3))
    return corners, centres


def _pair(values: Any) -> tuple[float, float]:
    return (float(values[0]), float(values[1]))


def _build_model(root: Path, manifest: Mapping[str, Any], height: np.ndarray,
                 river: np.ndarray) -> TrayModel:
    lv, fid, car = manifest["levels"], manifest["fiducials"], manifest["car"]
    corners, centres = _build_tags(manifest)
    size = tuple(float(v) for v in manifest["size_mm"])
    if len(size) != MM_DIMENSIONS or height.ndim != 2 or height.shape != river.shape:
        raise ValueError("unexpected size_mm or heightfield shape")
    return TrayModel(
        directory=root,
        name=str(manifest.get("name", root.name)),
        res_mm=float(manifest["res_mm"]),
        height_mm=_readonly(height),
        river=_readonly(river),
        size_mm=size,  # type: ignore[arg-type]
        floor_mm=float(lv["floor_mm"]),
        pool_mm=float(lv["pool_mm"]),
        step_mm=float(lv["step_mm"]),
        rim_top_mm=float(lv["rim_top_mm"]),
        levels=tuple(GaugeLevel(int(r["ft"]), float(r["level_mm"]), float(r["ml"]),
                                float(r["wet_fraction"])) for r in manifest["pour_table"]),
        tag_corners_mm=corners,
        tag_dictionary=str(fid["dictionary"]),
        tag_mm=float(fid["tag_mm"]),
        road=Road(**{k: float(manifest["road"][k]) for k in Road.__dataclass_fields__}),
        car=Car(_pair(car["centre_mm"]), float(car["road_mm"]), float(car["body_top_mm"]),
                float(car["roof_mm"])),
        houses=tuple(House(_pair(h["centre_mm"]), float(h["ground_mm"]), float(h["eave_mm"]),
                           float(h["ridge_mm"])) for h in manifest["houses"]),
        pad_mm=float(fid.get("pad_mm", 0.0)),
        tag_centres_mm=centres,
    )


def load_tray(directory: str | Path | None = None) -> TrayModel:
    """Load a tray build (``manifest.json`` + ``truth.npz``); works for the 160 and 200 mm builds."""
    root = Path(directory) if directory is not None else default_tray_dir()
    manifest_path, truth_path = root / MANIFEST_FILE, root / TRUTH_FILE
    for path in (manifest_path, truth_path):
        if not path.is_file():
            raise FileNotFoundError(f"gauge tray file missing: {path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with np.load(truth_path) as truth:
            height = truth["height_mm"].astype(np.float32)
            river = truth["river"].astype(bool)
        return _build_model(root, manifest, height, river)
    except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
        raise ValueError(f"malformed gauge tray data in {root}: {exc}") from exc


def level_ft(model: TrayModel, mm: float) -> float:
    """Flood level in feet above normal river height (pool = 0 ft)."""
    return (float(mm) - model.pool_mm) / model.step_mm


def level_mm(model: TrayModel, ft: float) -> float:
    """Inverse of :func:`level_ft`."""
    return model.pool_mm + float(ft) * model.step_mm
