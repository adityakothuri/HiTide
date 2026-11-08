import json
from datetime import datetime, timedelta

import pytest
from app.config import REPO_DIR
from feeds import local_sensors as local
from feeds.intake import split_response


def row(source):
    body=json.loads((REPO_DIR/"docs/examples/map-data"/f"{source}-excerpt.json").read_text(encoding="utf8"))
    req={"lcra_hydromet":local.LCRA,"hcfcd_water_levels":local.HARRIS,"txdot_cameras":local.CAMERAS}[source]
    payload={"features":[body]} if req.shape=="features" else [body]
    return split_response(req,{"source":"live","data":payload})[0]

def test_projection_preserves_sensor_times_and_excludes_timeless_camera_from_observation():
    for source in ("lcra_hydromet","hcfcd_water_levels"):
        r=row(source)
        preview=local.preview_local(r)
        assert preview["evidence_type"]=="measurement"
        assert datetime.fromisoformat(preview["time"]).utcoffset()==timedelta(0)
        assert preview["geometry"]["type"]=="Point"
    camera=local.preview_local(row("txdot_cameras"))
    assert camera["time"] is None and camera["evidence_type"]=="context"
    assert "capture time unavailable" in camera["detail"]

def test_wall_clock_dst_rejects_ambiguity_and_nonexistent_times():
    assert local.local_time("2026-11-01T01:30:00") is None
    assert local.local_time("2026-03-08T02:30:00") is None
    assert local.local_time("2026-11-07T22:31:30")=="2026-11-08T04:31:30+00:00"

@pytest.mark.asyncio
async def test_inundation_checks_actual_layer_availability_and_keeps_its_model_time(monkeypatch):
    calls=[]
    async def fetch(name,url,params,timeout):
        calls.append(url)
        return {"source":"live","data":len(calls)==2}
    monkeypatch.setattr(local,"fetch_live_page",fetch)
    [r]=await local.collect_inundation()
    assert len(calls)==2
    preview=local.preview_local(r)
    assert preview["evidence_type"]=="model"
    assert preview["time"]==local.local_time(r.raw_payload["layer_time_local"])
    assert preview["geometry"] is None
