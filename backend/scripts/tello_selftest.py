"""Unattended real-drone self-test. Does NOT fly. Writes results to ~/tello-test/.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello self-test" on the Desktop.
When it says DONE, reconnect to normal Wi-Fi and tell Claude "test done".
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import cv2
from djitellopy import Tello

sys.path.insert(0, str(Path(__file__).parent))
import tello_dashboard as dash  # noqa: E402

OUT = Path.home() / "tello-test"
REPORT = OUT / "report.txt"
VIDEO_SECONDS = 5
STATE_WAIT_SECONDS = 3
TEST_PORT = 8766
VIDEO_TIMEOUT = 30
DASHBOARD_TIMEOUT = 40

lines: list[str] = []


def log(text: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {text}"
    lines.append(line)
    print(line)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def step(name: str, fn) -> object:
    try:
        result = fn()
        log(f"PASS  {name}: {result}")
        return result
    except Exception as exc:
        log(f"FAIL  {name}: {exc.__class__.__name__}: {exc}")
        return None


def with_timeout(fn, seconds: int):
    """Run fn in a thread so a stuck video library can never freeze the test."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise TimeoutError(f"still waiting after {seconds}s (video decoder stuck)")
    if "error" in box:
        raise box["error"]
    return box["value"]


def wifi_name() -> str:
    out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True).stdout
    ssids = [l.split(":", 1)[1].strip() for l in out.splitlines() if l.strip().startswith("SSID")]
    if not any(s.upper().startswith("TELLO") for s in ssids):
        raise RuntimeError(f"not on Tello Wi-Fi (on {ssids})")
    return ssids[0]


def wait_for_state(tello: Tello) -> str:
    deadline = time.time() + STATE_WAIT_SECONDS
    while time.time() < deadline:
        state = tello.get_current_state()
        if state:
            return f"{len(state)} fields, bat={state.get('bat')} templ/h={state.get('templ')}/{state.get('temph')}"
        time.sleep(0.2)
    raise RuntimeError("no state packets on UDP 8890 (firewall is blocking Python?)")


def measure_video(tello: Tello) -> str:
    tello.streamon()
    reader = tello.get_frame_read()
    seen, last, first_at, start = 0, None, None, time.time()
    while time.time() - start < VIDEO_SECONDS:
        frame = reader.frame
        if frame is not None and frame is not last and frame.any():
            seen += 1
            last = frame
            first_at = first_at or time.time() - start
        time.sleep(0.005)
    if not seen:
        raise RuntimeError("no video frames on UDP 11111 (firewall is blocking Python?)")
    cv2.imwrite(str(OUT / "snapshot_as_dashboard.jpg"), cv2.cvtColor(last, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(OUT / "snapshot_raw.jpg"), last)
    return f"{seen / VIDEO_SECONDS:.1f} fps, first frame after {first_at:.1f}s, shape {last.shape}"


def test_dashboard(tello: Tello) -> str:
    drone = dash.Drone(tello)
    drone.start()
    server = dash.ThreadingHTTPServer(("127.0.0.1", TEST_PORT), dash.make_handler(drone))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{TEST_PORT}"
    status = json.loads(urllib.request.urlopen(f"{base}/status", timeout=5).read())
    if "error" in status:
        raise RuntimeError(status["error"])
    stream = urllib.request.urlopen(f"{base}/video", timeout=5)
    data, start = b"", time.time()
    while time.time() - start < 3:
        data += stream.read(4096)
    frames = data.count(b"--frame")
    urllib.request.urlopen(urllib.request.Request(f"{base}/rc", data=b'{"fb":0}', method="POST"), timeout=5)
    server.shutdown()
    if frames == 0:
        raise RuntimeError("dashboard served no video frames")
    return f"status ok (battery {status['battery']}%, temp {status['temp']}C), {frames / 3:.1f} fps over HTTP"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    log("Tello self-test (no flight)")
    step("Wi-Fi", wifi_name)
    tello = Tello()
    if step("Drone answers commands", lambda: tello.connect(wait_for_state=False) or dash.flush_replies(tello) or "ok") is None:
        log("DONE: drone did not answer. Check Wi-Fi and power, then run again.")
        return
    for label, command in [("Battery %", "battery?"), ("Temperature", "temp?"),
                            ("Wi-Fi SNR", "wifi?"), ("Attitude", "attitude?")]:
        step(label, lambda c=command: tello.send_read_command(c))
    step("State packets (UDP 8890)", lambda: wait_for_state(tello))
    log(f"...starting video, this can take up to {VIDEO_TIMEOUT}s. Please wait.")
    video_ok = step("Video stream (UDP 11111)", lambda: with_timeout(lambda: measure_video(tello), VIDEO_TIMEOUT))
    if video_ok:
        log(f"...testing the dashboard, up to {DASHBOARD_TIMEOUT}s. Please wait.")
        step("Dashboard end-to-end", lambda: with_timeout(lambda: test_dashboard(tello), DASHBOARD_TIMEOUT))
    else:
        log("SKIP  Dashboard end-to-end: video did not work")
    try:
        with_timeout(lambda: (tello.streamoff(), tello.end()), 10)
    except Exception:
        pass
    fails = sum(1 for l in lines if "FAIL" in l)
    log(f"DONE: {fails} failure(s). Results in {OUT}")


if __name__ == "__main__":
    main()
    os._exit(0)  # don't wait on a stuck video thread
