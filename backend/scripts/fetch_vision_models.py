"""Save SegFormer-B0 (ADE20K) and YOLOv8n under data/models/ so the demo runs offline.

Run once with network: `cd backend && uv run python scripts/fetch_vision_models.py`
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR
from vision.config import vision_config

log = logging.getLogger("fetch_vision_models")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

    cfg = vision_config()["models"]
    out = DATA_DIR / cfg["segformer_dir"]
    out.mkdir(parents=True, exist_ok=True)
    SegformerImageProcessor.from_pretrained(cfg["segformer_hub_id"]).save_pretrained(out)
    model = SegformerForSemanticSegmentation.from_pretrained(cfg["segformer_hub_id"])
    model.save_pretrained(out)
    log.info("saved %s -> %s (%d labels)", cfg["segformer_hub_id"], out, len(model.config.id2label))

    from transformers import CLIPSegForImageSegmentation, CLIPSegProcessor

    clip_out = DATA_DIR / cfg["clipseg_dir"]
    CLIPSegProcessor.from_pretrained(cfg["clipseg_hub_id"]).save_pretrained(clip_out)
    CLIPSegForImageSegmentation.from_pretrained(cfg["clipseg_hub_id"]).save_pretrained(clip_out)
    log.info("saved %s -> %s", cfg["clipseg_hub_id"], clip_out)

    from vision.detect import _model

    _model()  # downloads yolov8n.pt into data/models/ if missing
    log.info("yolo ready at %s", DATA_DIR / cfg["yolo"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
