"""Temporary source display projections, independent of storage and normalization."""

from feeds.intake import RawEnvelope
from feeds.local_sensors import preview_local
from feeds.noaa_products import preview_noaa
from feeds.regional_roads import preview_regional

LABELS = {
    "noaa_mrms": "NOAA rainfall estimates",
    "noaa_flash": "NOAA runoff guidance",
    "noaa_nwps": "NOAA river observations",
    "lcra_hydromet": "LCRA rainfall and river levels",
    "hcfcd_water_levels": "Harris County water levels",
    "hcfcd_inundation": "Harris County inundation",
    "txdot_cameras": "TxDOT camera inventory",
    "atx_flood_closures": "Austin flood closures",
    "sariver_crossings": "San Antonio basin crossings",
    "transtar_incidents": "TranStar incidents",
    "transtar_lane_closures": "TranStar lane closures",
    "transtar_flood_risk": "TranStar roadway flood risk",
}
NOTES = {
    "txdot_cameras": "Camera locations are context. Image capture times and visible road conditions require verification.",
    "atx_flood_closures": "The provider schema omits observation timestamps.",
    "sariver_crossings": "Provider timestamps omit timezone offsets. Statuses are available as context.",
    "transtar_incidents": "Live feed access requires contacting Houston TranStar.",
    "transtar_lane_closures": "Live feed access requires contacting Houston TranStar.",
    "transtar_flood_risk": "Live feed access requires contacting Houston TranStar.",
    "noaa_mrms": "Estimated rainfall. Values do not measure road water depth.",
    "noaa_flash": "Modeled runoff guidance. Values do not establish road closure or pavement depth.",
    "hcfcd_inundation": "Estimated inundation around monitored waterways. Model time determines eligibility.",
}


def preview(raw: RawEnvelope) -> dict | None:
    """Malformed input stays raw with a disposition, without breaking other sources."""
    try:
        for project in (preview_noaa, preview_local, preview_regional):
            result = project(raw)
            if result is not None:
                return result
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
        return None
    return None
