"""NWS Local Storm Reports for Texas as distributed by Iowa Environmental Mesonet."""

import re
from datetime import UTC, datetime, timedelta

from feeds.base import fetch_live_page
from feeds.intake import FeedRequest, RawEnvelope, split_response

SOURCE_ID = "nws_local_storm_reports"
LSR_URL = "https://mesonet.agron.iastate.edu/geojson/lsr.geojson"
ROAD_MENTION = re.compile(
    r"\b(?:roads?|roadways?|streets?|highways?|interstates?|freeways?|"
    r"underpasses?|bridges?|crossings?|avenues?|boulevards?|lanes?|"
    r"rd|st|hwy|ave|blvd)\b|\b(?:fm|sh|ih|us|i)[ -]?\d+\b",
    re.IGNORECASE,
)


async def collect_texas_road_reports() -> list[RawEnvelope]:
    """Collect the whole state's rolling 30-minute batch, including empty attempts."""
    end = datetime.now(UTC)
    start = end - timedelta(minutes=30)
    request = FeedRequest(
        SOURCE_ID, "texas_lsr", LSR_URL,
        {"states": "TX", "sts": start.strftime("%Y-%m-%dT%H:%MZ"),
         "ets": end.strftime("%Y-%m-%dT%H:%MZ")},
        {"state": "TX"}, "features",
    )
    response = await fetch_live_page(request.product, request.url, request.params, request.timeout_s)
    return split_response(request, response)


def road_report_exclusion(raw: RawEnvelope) -> str | None:
    """Select Texas flood reports that mention a road. Access and depth remain unknown."""
    props = raw.raw_payload.get("properties") if isinstance(raw.raw_payload, dict) else None
    if not isinstance(props, dict):
        return "missing_properties"
    if props.get("state") != "TX":
        return "outside_scope"
    if props.get("typetext") not in ("FLOOD", "FLASH FLOOD", "COASTAL FLOOD", "LAKESHORE FLOOD"):
        return "other_hazard"
    remark = props.get("remark")
    if not isinstance(remark, str) or not ROAD_MENTION.search(remark):
        return "no_road_mention"
    return None
