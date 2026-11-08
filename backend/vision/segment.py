"""Water and scene segmentation: SegFormer-B0 (ADE20K, pretrained, no training) + HSV colour fallback.

Class ids are resolved by NAME so a different checkpoint can't silently shift them; the static table
below is the standard ADE20K-150 order and a test asserts it equals the real model's id2label.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Mapping

import cv2
import numpy as np

from app.config import DATA_DIR
from vision.config import vision_config
from vision.grid import Seg, group_lut

log = logging.getLogger(__name__)

ADE20K_NAMES: tuple[str, ...] = (
    "wall", "building", "sky", "floor", "tree", "ceiling", "road", "bed", "windowpane", "grass", "cabinet",
    "sidewalk", "person", "earth", "door", "table", "mountain", "plant", "curtain", "chair", "car", "water",
    "painting", "sofa", "shelf", "house", "sea", "mirror", "rug", "field", "armchair", "seat", "fence", "desk",
    "rock", "wardrobe", "lamp", "bathtub", "railing", "cushion", "base", "box", "column", "signboard",
    "chest of drawers", "counter", "sand", "sink", "skyscraper", "fireplace", "refrigerator", "grandstand",
    "path", "stairs", "runway", "case", "pool table", "pillow", "screen door", "stairway", "river", "bridge",
    "bookcase", "blind", "coffee table", "toilet", "flower", "book", "hill", "bench", "countertop", "stove",
    "palm", "kitchen island", "computer", "swivel chair", "boat", "bar", "arcade machine", "hovel", "bus",
    "towel", "light", "truck", "tower", "chandelier", "awning", "streetlight", "booth", "television receiver",
    "airplane", "dirt track", "apparel", "pole", "land", "bannister", "escalator", "ottoman", "bottle",
    "buffet", "poster", "stage", "van", "ship", "fountain", "conveyer belt", "canopy", "washer", "plaything",
    "swimming pool", "stool", "barrel", "basket", "waterfall", "tent", "bag", "minibike", "cradle", "oven",
    "ball", "food", "step", "tank", "trade name", "microwave", "pot", "animal", "bicycle", "lake",
    "dishwasher", "screen", "blanket", "sculpture", "hood", "sconce", "vase", "traffic light", "tray",
    "ashcan", "fan", "pier", "crt screen", "plate", "monitor", "bulletin board", "shower", "radiator",
    "glass", "clock", "flag",
)


def ids_by_group(names: tuple[str, ...] = ADE20K_NAMES, classes: Mapping[str, Any] | None = None) -> dict[str, set[int]]:
    """{'water': {21, 26, ...}, 'ground': {...}, 'blocker': {...}, 'road': {...}} from config class names."""
    classes = classes or vision_config()["classes"]
    index = {n: i for i, n in enumerate(names)}
    out: dict[str, set[int]] = {}
    for group, wanted in classes.items():
        missing = [w for w in wanted if w not in index]
        if missing:
            log.warning("vision classes not in label set (%s): %s", group, missing)
        out[group] = {index[w] for w in wanted if w in index}
    return out


def lut_from_names(names: tuple[str, ...] = ADE20K_NAMES) -> np.ndarray:
    return group_lut(ids_by_group(names))


def is_low_light(frame_bgr: np.ndarray, threshold: float | None = None) -> bool:
    thr = vision_config()["segmentation"]["low_light_v"] if threshold is None else threshold
    v = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
    return float(v.mean()) < thr


def color_fallback(frame_bgr: np.ndarray) -> np.ndarray:
    """HSV mask for the blue demo sheet/tray (bool, h x w)."""
    cfg = vision_config()["segmentation"]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(cfg["hsv_lo"], np.uint8), np.array(cfg["hsv_hi"], np.uint8)) > 0


def clean_water(mask: np.ndarray, min_blob_frac: float) -> np.ndarray:
    """Opening (remove specks), closing (fill small holes), drop blobs under min_blob_frac of the frame."""
    m = mask.astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    min_px = min_blob_frac * m.size
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return keep[cc]


def _device(pref: str) -> str:
    import torch

    if pref != "auto":
        return pref
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


@lru_cache(maxsize=1)
def _load_segformer() -> tuple[Any, Any, str, tuple[str, ...]]:
    """Local weights only (offline demo). Run scripts/fetch_vision_models.py once to save them."""
    import torch  # noqa: F401  heavy import, only when segmenting
    from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

    cfg = vision_config()["models"]
    path = DATA_DIR / cfg["segformer_dir"]
    if not path.is_dir():
        raise FileNotFoundError(f"{path} missing: run `uv run python scripts/fetch_vision_models.py`")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    proc = SegformerImageProcessor.from_pretrained(path, local_files_only=True)
    model = SegformerForSemanticSegmentation.from_pretrained(path, local_files_only=True)
    device = _device(cfg["device"])
    model = model.to(device).eval()
    id2label = model.config.id2label
    names = tuple(id2label[i].strip() for i in range(len(id2label)))
    return proc, model, device, names


@lru_cache(maxsize=1)
def _load_clipseg() -> tuple[Any, Any, str]:
    from transformers import CLIPSegForImageSegmentation, CLIPSegProcessor

    cfg = vision_config()["models"]
    path = DATA_DIR / cfg["clipseg_dir"]
    if not path.is_dir():
        raise FileNotFoundError(f"{path} missing: run `uv run python scripts/fetch_vision_models.py`")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    proc = CLIPSegProcessor.from_pretrained(path, local_files_only=True)
    device = _device(cfg["device"])
    model = CLIPSegForImageSegmentation.from_pretrained(path, local_files_only=True).to(device).eval()
    return proc, model, device


class ZeroShotWater:
    """CLIPSeg text-prompted water probability. ADE20K-trained SegFormer calls muddy floodwater
    'earth' / 'road' / 'dirt track'; a zero-shot prompt for flood water recovers it (pretrained only,
    overview 9.4). Probability = softmax share of the water prompts against scene prompts."""

    def __init__(self) -> None:
        self.cfg = vision_config()["segmentation"]["zero_shot"]
        self.proc, self.model, self.device = _load_clipseg()
        self.prompts = list(self.cfg["water_prompts"]) + list(self.cfg["scene_prompts"])
        self.n_water = len(self.cfg["water_prompts"])

    def run(self, rgb: np.ndarray) -> np.ndarray:
        import torch

        h, w = rgb.shape[:2]
        inp = self.proc(text=self.prompts, images=[rgb] * len(self.prompts), padding=True, return_tensors="pt")
        with torch.inference_mode():
            logits = self.model(**inp.to(self.device)).logits.float()
            share = logits.softmax(dim=0)[: self.n_water].sum(dim=0)
            share = torch.nn.functional.interpolate(share[None, None], size=(h, w), mode="bilinear",
                                                    align_corners=False)[0, 0]
        return share.cpu().numpy()


class Segmenter:
    """SegFormer (sharp boundaries) + optional zero-shot flood water + optional colour fallback.

    run(frame) -> Seg(labels, p_water, low_light, zero_shot_frac).
    """

    def __init__(self, zero_shot: bool | None = None, color_fallback: bool | None = None) -> None:
        self.cfg = vision_config()["segmentation"]
        self.color_fallback = bool(self.cfg["color_fallback"] if color_fallback is None else color_fallback)
        self.proc, self.model, self.device, self.names = _load_segformer()
        groups = ids_by_group(self.names)
        self.water_ids = sorted(groups["water"])
        self.lut = group_lut(groups, n=len(self.names))
        hard = {"car", "truck", "bus", "van", "person", "boat", "ship", "bicycle", "minibike"}
        self.hard_veto = np.array([n.strip() in hard for n in self.names] + [False])
        use_zs = self.cfg["zero_shot"]["enabled"] if zero_shot is None else zero_shot
        self.zero_shot = ZeroShotWater() if use_zs else None
        self._zs_every = int(self.cfg["zero_shot"]["every_n"])
        self._calls = 0
        self._zs_last: np.ndarray | None = None

    def reset(self) -> None:
        """Start a new scene/hover: drop the cached zero-shot mask so it can't leak across scenes."""
        self._calls, self._zs_last = 0, None

    def _zero_shot(self, rgb: np.ndarray) -> np.ndarray | None:
        if self.zero_shot is None:
            return None
        stale = self._zs_last is None or self._zs_last.shape != rgb.shape[:2]
        if stale or self._calls % self._zs_every == 0:
            self._zs_last = self.zero_shot.run(rgb)
        return self._zs_last

    def run(self, frame_bgr: np.ndarray) -> Seg:
        import torch

        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        side = int(self.cfg["input_px"])
        inputs = self.proc(images=rgb, return_tensors="pt", size={"height": side, "width": side})
        with torch.inference_mode():
            # softmax/argmax at the model's native 1/4 resolution; upsampling 150 channels to full frame
            # costs ~0.7 GB at 1280x960 and thrashes MPS memory. Only the water channel is upsampled.
            logits = self.model(pixel_values=inputs["pixel_values"].to(self.device)).logits
            prob = logits.softmax(dim=1)
            p_small = prob[:, self.water_ids].sum(dim=1, keepdim=True)
            top, arg = prob.max(dim=1)
            lab_small = arg.to(torch.int16)[0].cpu().numpy()
            conf_small = top[0].float().cpu().numpy()
            p_water = torch.nn.functional.interpolate(p_small, size=(h, w), mode="bilinear",
                                                      align_corners=False)[0, 0].float().cpu().numpy()
        labels = cv2.resize(lab_small, (w, h), interpolation=cv2.INTER_NEAREST)
        conf = cv2.resize(conf_small, (w, h), interpolation=cv2.INTER_NEAREST)
        base = p_water >= 0.5
        water = base.copy()
        zs = self._zero_shot(rgb)
        self._calls += 1
        if zs is not None:
            # zero-shot may add water, but never over a confident blocker (car, person, tree, sky, ...)
            from vision.grid import BLOCKER

            # only a CONFIDENT blocker vetoes it: SegFormer calls calm aerial river 'wall'/'plant' at low confidence
            sure = conf >= float(self.cfg["zero_shot"].get("blocker_veto_conf", 0.0))
            veto = (self.lut[labels] == BLOCKER) & (sure | self.hard_veto[labels])   # cars/people: always
            zs = np.where(veto, 0.0, zs)
            water |= zs >= 0.5
            p_water = np.maximum(p_water, zs)
        if self.color_fallback:
            water |= color_fallback(frame_bgr)
        water = clean_water(water, float(self.cfg["min_blob_frac"]))
        n_water = int(water.sum())
        zs_frac = float((water & ~base).sum() / n_water) if n_water else 0.0
        # keep the probability consistent with the cleaned mask (soft inside a 0.5 band at the boundary)
        p_water = np.where(water, np.maximum(p_water, 0.5), np.minimum(p_water, 0.4999)).astype(np.float32)
        return Seg(labels, p_water, is_low_light(frame_bgr), zs_frac)
