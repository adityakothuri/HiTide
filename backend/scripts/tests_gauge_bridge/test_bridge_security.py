"""Drive-by browser attacks against the local bridge must not reach the drone.

A page in the demo browser can send "simple" cross-origin POSTs (text/plain, no preflight) to
127.0.0.1, and a DNS-rebinding page arrives with a foreign Host header. Runs a real server.
"""

import http.client
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dash = pytest.importorskip("tello_dashboard")


class FakeDrone:
    jpeg = b"\xff\xd8fake\xff\xd9"

    def __init__(self):
        self.actions: list[str] = []
        self.rc: list[dict] = []

    def action(self, name: str) -> str:
        self.actions.append(name)
        return "ok"

    def set_rc(self, values: dict) -> None:
        self.rc.append(values)

    def status(self) -> dict:
        return {"connected": True}


@pytest.fixture
def bridge():
    drone = FakeDrone()
    server = dash.DashboardServer(("127.0.0.1", 0), dash.make_handler(drone, None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield drone, server.server_address[1]
    server.shutdown()
    server.server_close()


def request(port: int, method: str, path: str, body: bytes = b"", **headers: str) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host="Host" in headers)
    for key, value in {"Content-Length": str(len(body)), **headers}.items():
        conn.putheader(key, value)
    conn.endheaders(body)
    status = conn.getresponse().status
    conn.close()
    return status


JSON = {"Content-Type": "application/json"}


def test_legit_json_post_from_the_dashboard_works(bridge):
    drone, port = bridge
    assert request(port, "POST", "/action/land", b"{}", Origin=f"http://127.0.0.1:{port}", **JSON) == 200
    assert drone.actions == ["land"]


def test_backend_proxy_request_without_origin_works(bridge):
    drone, port = bridge
    assert request(port, "POST", "/action/takeoff", b"{}", **JSON) == 200
    assert drone.actions == ["takeoff"]


def test_simple_text_plain_post_cannot_take_off(bridge):
    drone, port = bridge
    status = request(port, "POST", "/action/takeoff", b"{}", Origin="https://evil.example",
                     **{"Content-Type": "text/plain"})
    assert status in (403, 415)
    assert drone.actions == []


def test_text_plain_without_origin_is_refused(bridge):
    drone, port = bridge
    assert request(port, "POST", "/action/emergency", b"{}", **{"Content-Type": "text/plain"}) == 415
    assert drone.actions == []


def test_foreign_origin_with_json_is_refused(bridge):
    drone, port = bridge
    assert request(port, "POST", "/rc", b'{"fb": 50}', Origin="https://evil.example", **JSON) == 403
    assert drone.rc == []


def test_dns_rebinding_host_is_refused_for_reads_and_writes(bridge):
    drone, port = bridge
    assert request(port, "GET", "/status", Host=f"evil.example:{port}") == 403
    assert request(port, "POST", "/action/takeoff", b"{}", Host=f"evil.example:{port}", **JSON) == 403
    assert drone.actions == []


def test_cross_site_embedding_of_the_camera_feed_is_refused(bridge):
    _, port = bridge
    assert request(port, "GET", "/video", **{"Sec-Fetch-Site": "cross-site"}) == 403


def test_shutdown_cannot_be_triggered_by_a_drive_by_page(bridge):
    _, port = bridge
    assert request(port, "POST", "/shutdown", b"{}", **{"Content-Type": "text/plain"}) == 415
    assert request(port, "GET", "/status") == 200  # still running


def test_non_object_json_body_is_rejected(bridge):
    drone, port = bridge
    assert request(port, "POST", "/rc", b"[1, 2]", **JSON) == 400
    assert drone.rc == []


def test_bad_content_length_is_rejected(bridge):
    _, port = bridge
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/rc")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", "abc")
    conn.endheaders()
    assert conn.getresponse().status == 400
    conn.close()
