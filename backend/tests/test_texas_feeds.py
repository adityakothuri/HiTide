import pytest

from feeds import texas


def live(payload):
    return {"source": "live", "data": payload, "fetched_at": "2026-11-08T04:05:00Z"}


@pytest.mark.asyncio
async def test_usgs_cursor_keeps_texas_filters_and_page_provenance(monkeypatch):
    requests = []
    url = texas.TEXAS_GAGES.url

    async def fetch(product, endpoint, params, timeout):
        requests.append((endpoint, params))
        if "cursor" in params:
            return live({"features": [{"id": "other-station-reading"}]})
        return live(
            {
                "features": [{"id": "reading"}],
                "links": [{"rel": "next", "href": f"{url}?cursor=two&state_code=99"}],
            }
        )

    monkeypatch.setattr(texas, "fetch_live_page", fetch)
    first, second = await texas.collect_texas_gages()
    assert requests == [
        (url, texas.TEXAS_GAGES.params),
        (url, {**texas.TEXAS_GAGES.params, "cursor": "two"}),
    ]
    assert first.attempt_id != second.attempt_id
    assert first.request_params["state_code"] == "48"
    assert first.geographic_scope["state"] == "TX"
    assert second.provider_metadata["page"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "limit", "error"),
    [
        ("?cursor=repeats", 4, "repeated_page_cursor"),
        ("?cursor=first", 1, "page_limit_reached"),
        ("https://example.com/next?cursor=oops", 2, "invalid_next_page"),
        ("?area=TX", 2, "invalid_next_page"),
    ],
)
async def test_unfinished_statewide_poll_emits_marker(
    monkeypatch, target, limit, error
):
    async def fetch(*args):
        return live({"features": [{"id": "cap"}], "pagination": {"next": target}})

    monkeypatch.setattr(texas, "MAX_PAGES", limit)
    monkeypatch.setattr(texas, "fetch_live_page", fetch)
    rows = await texas.collect_texas_alerts()
    assert rows[0].request_params == {"area": "TX"}
    assert rows[0].retrieval_status == "success"
    assert rows[-1].retrieval_status == "failed" and rows[-1].errors == (error,)


@pytest.mark.asyncio
async def test_outage_after_first_page_preserves_first_page(monkeypatch):
    async def fetch(name, endpoint, params, timeout):
        if "cursor" in params:
            return {"source": "unavailable", "data": None, "errors": ("http_503",)}
        return live(
            {"features": [{"id": "cap"}], "pagination": {"next": "?cursor=next"}}
        )

    monkeypatch.setattr(texas, "fetch_live_page", fetch)
    row, failure = await texas.collect_texas_alerts()
    assert row.raw_payload == {"id": "cap"}
    assert failure.provenance == "unavailable" and failure.errors == ("http_503",)
    assert failure.provider_metadata["page"] == 2
