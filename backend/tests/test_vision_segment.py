"""Segmentation: class ids by name, colour fallback, cleaning, and real flood photos (overview 9.4, 22)."""

import json

import cv2
import numpy as np
import pytest

from app.config import DATA_DIR
from vision.config import vision_config
from vision.segment import ADE20K_NAMES, clean_water, color_fallback, ids_by_group, is_low_light

MODELS = DATA_DIR / "models"
needs_models = pytest.mark.skipif(
    not (MODELS / "segformer-b0-ade").is_dir() or not (MODELS / "clipseg-rd64").is_dir(),
    reason="run scripts/fetch_vision_models.py",
)


def test_overview_class_ids_resolve_by_name():
    g = ids_by_group()
    assert {21, 26, 60} <= g["water"]               # water, sea, river (overview 9.4)
    assert 6 in g["road"] and 6 in g["ground"]       # road
    assert {20, 12} <= g["blocker"]                  # car, person
    assert ADE20K_NAMES[128] == "lake" and 128 in g["water"]


def test_static_table_matches_the_shipped_model_config():
    cfg = MODELS / "segformer-b0-ade" / "config.json"
    if not cfg.is_file():
        pytest.skip("run scripts/fetch_vision_models.py")
    id2label = json.loads(cfg.read_text())["id2label"]
    assert tuple(id2label[str(i)].strip() for i in range(150)) == ADE20K_NAMES


def test_colour_fallback_finds_a_blue_sheet_and_not_grey_road():
    img = np.full((120, 160, 3), (110, 110, 110), np.uint8)       # grey "road" (BGR)
    img[30:90, 40:120] = (200, 90, 20)                             # blue sheet
    m = color_fallback(img)
    assert m[30:90, 40:120].mean() > 0.95 and m[:20].mean() == 0


def test_colour_fallback_is_off_by_default_for_real_footage():
    assert vision_config()["segmentation"]["color_fallback"] is False


def test_clean_water_drops_specks_and_keeps_real_water():
    m = np.zeros((100, 100), bool)
    m[40:80, 10:90] = True          # lake
    m[5, 5] = m[10:12, 50:52] = True  # glare specks
    out = clean_water(m, 0.01)
    assert out[60, 50] and not out[5, 5] and not out[11, 51]


def test_low_light_flag():
    assert is_low_light(np.full((10, 10, 3), 20, np.uint8))
    assert not is_low_light(np.full((10, 10, 3), 180, np.uint8))


@pytest.fixture(scope="module")
def segmenter():
    from vision.segment import Segmenter

    s = Segmenter()
    s._zs_every = 1        # run the zero-shot model on every image here
    return s


@needs_models
def test_real_flood_photos_show_water(segmenter):
    """overview 22: the pipeline run on real flood images must flag water. flood_08 (night, wet asphalt
    in a car park) is a documented miss for both models; everything else must find >= 20% water."""
    found = {}
    for i in range(1, 9):
        img = cv2.imread(str(DATA_DIR / "drone_samples" / f"flood_0{i}.jpg"))
        found[i] = float((segmenter.run(img).p_water >= 0.5).mean())
    hits = [i for i, f in found.items() if f >= 0.20]
    assert len(hits) >= 7, found
    assert set(range(1, 8)) <= set(hits), found


@needs_models
def test_zero_shot_never_paints_water_over_a_detected_car(segmenter):
    img = cv2.imread(str(DATA_DIR / "drone_samples" / "flood_07.jpg"))
    seg = segmenter.run(img)
    car = seg.labels == ADE20K_NAMES.index("car")
    assert car.sum() > 500
    assert (seg.p_water[car] >= 0.5).mean() < 0.05
