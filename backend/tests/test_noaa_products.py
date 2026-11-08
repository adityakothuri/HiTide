import gzip
from datetime import UTC, datetime

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from feeds import noaa_products as noaa


def test_newest_grid_uses_immutable_product_time():
    html = '<a href="MRMS_PrecipRate.latest.grib2.gz">latest</a>'
    html += '<a href="MRMS_PrecipRate_00.00_20261108-043200.grib2.gz">data</a>'
    assert noaa.newest_grib_reference(html, "MRMS_PrecipRate") == (
        "MRMS_PrecipRate_00.00_20261108-043200.grib2.gz", "2026-11-08T04:32:00+00:00")
    assert noaa.newest_grib_reference("latest only", "MRMS_PrecipRate") is None


def test_grid_decode_excludes_negative_missing_and_preserves_product_time():
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", height=2, width=2, count=1, dtype="float32",
                         crs="EPSG:4326", transform=from_origin(-100.25, 30.25, .25, .25)) as dataset:
            dataset.write(np.array([[-9999, 2], [5, 0]], dtype="float32"), 1)
            dataset.update_tags(1, GRIB_VALID_TIME=str(int(datetime(2026, 11, 8, 4, 30, tzinfo=UTC).timestamp())),
                                GRIB_UNIT="[mm/hr]")
        data = memory.read()
    samples = noaa.decode_texas_grid(gzip.compress(data))
    sample = next(s for s in samples if s["geometry"]["coordinates"] == [-100.0, 30.0])
    assert sample["value"] == 5 and sample["unit"] == "[mm/hr]"
    assert sample["time"] == "2026-11-08T04:30:00+00:00"


@pytest.mark.asyncio
async def test_nwps_state_filter_missing_values_and_shared_attempt(monkeypatch):
    base = {"lid": "TX1", "name": "Texas station", "state": {"abbreviation": "TX"},
            "latitude": 30, "longitude": -98,
            "status": {"observed": {"primary": 2, "primaryUnit": "ft", "validTime": "2026-11-08T04:30:00Z"}}}
    async def fetch(*args):
        return {"source": "live", "data": {"gauges": [base, {**base, "lid": "TX2"},
            {**base, "state": {"abbreviation": "NM"}}]}}
    monkeypatch.setattr(noaa, "fetch_live_page", fetch)
    rows = await noaa.collect_nwps()
    assert len(rows) == 2 and rows[0].attempt_id == rows[1].attempt_id
    assert noaa.preview_noaa(rows[0])["geometry"]["coordinates"] == [-98, 30]
    rows[0].raw_payload["status"]["observed"]["primary"] = -999
    assert noaa.preview_noaa(rows[0]) is None
