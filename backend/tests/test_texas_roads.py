import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.config import REPO_DIR
from feeds import texas_roads


@pytest.mark.asyncio
async def test_texas_lsr_request_and_report_mapping(monkeypatch):
    fixture = REPO_DIR / "docs/examples/map-data/texas-lsr-road-excerpt.json"

    async def fetch(name, url, params, timeout):
        assert params["states"] == "TX"
        start = datetime.fromisoformat(params["sts"])
        end = datetime.fromisoformat(params["ets"])
        assert end - start == timedelta(minutes=30)
        return {"source": "live", "data": json.loads(fixture.read_text())}

    monkeypatch.setattr(texas_roads, "fetch_live_page", fetch)
    [record] = await texas_roads.collect_texas_road_reports()
    props = record.raw_payload["properties"]
    assert record.source_id == texas_roads.SOURCE_ID
    assert texas_roads.road_report_exclusion(record) is None
    assert props["valid"] == "2026-09-02T11:08:00Z"
    assert props["magf"] is None and "6-8 inches" in props["remark"]
    for changes, expected in [
        ({"state": "LA"}, "outside_scope"),
        ({"typetext": "RAIN"}, "other_hazard"),
        ({"remark": "Creek at bankfull"}, "no_road_mention"),
        ({"remark": None}, "no_road_mention"),
    ]:
        changed = replace(record, raw_payload={"properties": {**props, **changes}})
        assert texas_roads.road_report_exclusion(changed) == expected
