"""SpacetimeDB HTTP client: decoding, quoting, auth header, error mapping (no server: httpx.MockTransport)."""

import json

import httpx
import pytest

from db.spacetime import NONE, SpacetimeClient, SpacetimeConfig, SpacetimeError, decode_rows, ident, opt, quote, some

OPT_F64 = {"Sum": {"variants": [{"name": {"some": "some"}, "algebraic_type": {"F64": []}},
                                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}}]}}
TS = {"Product": {"elements": [{"name": {"some": "__timestamp_micros_since_unix_epoch__"}, "algebraic_type": {"I64": []}}]}}


def _client(handler) -> SpacetimeClient:
    return SpacetimeClient(SpacetimeConfig("http://st.test", "floodwatch", "tok123"), transport=httpx.MockTransport(handler))


def test_decode_rows_options_timestamps_arrays():
    result = {"schema": {"elements": [
        {"name": {"some": "id"}, "algebraic_type": {"String": []}},
        {"name": {"some": "lon"}, "algebraic_type": OPT_F64},
        {"name": {"some": "at"}, "algebraic_type": TS},
        {"name": {"some": "tags"}, "algebraic_type": {"Array": {"String": []}}}]},
        "rows": [["a", [0, -99.1], [1_500_000], ["x", "y"]], ["b", [1, []], [0], []]]}
    assert decode_rows(result) == [{"id": "a", "lon": -99.1, "at": 1.5, "tags": ["x", "y"]},
                                   {"id": "b", "lon": None, "at": 0.0, "tags": []}]


def test_quote_and_ident_block_injection():
    assert quote("O'Brien") == "'O''Brien'"
    assert quote("x'; DROP TABLE kv; --") == "'x''; DROP TABLE kv; --'"
    with pytest.raises(ValueError):
        quote("a\x00b")
    with pytest.raises(TypeError):
        quote(5)  # type: ignore[arg-type]
    assert ident("danger_latest") == "danger_latest"
    for bad in ("kv; DROP", "1abc", "a b", ""):
        with pytest.raises(ValueError):
            ident(bad)


def test_option_args():
    assert opt(None) == NONE == {"none": []}
    assert opt(0.0) == some(0.0) == {"some": 0.0}


def test_call_sends_positional_json_and_bearer_token():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(path=req.url.path, auth=req.headers.get("authorization"), body=json.loads(req.content))
        return httpx.Response(200)

    _client(handler).call("kv_set", "k", "v")
    assert seen == {"path": "/v1/database/floodwatch/call/kv_set", "auth": "Bearer tok123", "body": ["k", "v"]}


def test_reducer_rejection_and_bad_sql_raise_with_message():
    c = _client(lambda req: httpx.Response(530, text="only the HiTide backend may write"))
    with pytest.raises(SpacetimeError, match="only the HiTide backend may write") as e:
        c.call("kv_set", "k", "v")
    assert e.value.status == 530
    with pytest.raises(SpacetimeError, match="SQL failed"):
        _client(lambda req: httpx.Response(400, text="no such table")).sql("SELECT * FROM nope")


def test_unreachable_server_is_a_typed_error():
    def boom(req):
        raise httpx.ConnectError("refused")

    c = _client(boom)
    with pytest.raises(SpacetimeError, match="unreachable"):
        c.sql("SELECT 1")
    assert c.ping() is False


def test_nan_is_never_sent():
    c = _client(lambda req: httpx.Response(200))
    with pytest.raises(ValueError):
        c.call("upsert_dangers", float("nan"))


def test_token_is_not_in_public_config():
    assert SpacetimeConfig("http://x", "db", "secret").public() == {"url": "http://x", "database": "db", "authenticated": True}


def test_timeouts_are_not_retried_but_connect_errors_are():
    calls = {"n": 0}

    def slow(req):
        calls["n"] += 1
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SpacetimeError, match="request failed"):
        _client(slow).call("enroll_user", "{}")
    assert calls["n"] == 1   # a timed-out reducer may have committed: never sent twice

    calls["n"] = 0

    def refused_then_ok(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200)

    _client(refused_then_ok).call("kv_set", "k", "v")
    assert calls["n"] == 2
