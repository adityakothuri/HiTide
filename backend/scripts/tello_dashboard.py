"""Unified Tello dashboard: live video, telemetry, and keyboard/mouse flight control in a browser.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello dashboard" on the Desktop.
It opens http://127.0.0.1:8765 in your browser. Works offline. Press Ctrl+C in the console to stop
(the drone lands first if it is flying).
"""

import json
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
from djitellopy import Tello

HOST, PORT = "127.0.0.1", 8765
PAGE = Path(__file__).with_name("tello_dashboard.html")
LOG_FILE = Path.home() / "tello-test" / "dashboard.log"
RC_HZ = 20
DEADMAN_SECONDS = 0.6  # stop moving if the browser stops sending controls
FRAME_SECONDS = 1 / 30
JPEG_QUALITY = 70
RC_LIMIT = 100
ACTIONS = ("takeoff", "land", "emergency")
FLUSH_WAIT_SECONDS = 0.3
TAKEOFF_TIMEOUT = 20
STATE_STALE_SECONDS = 2.0  # no telemetry for this long = drone connection lost
VIDEO_STALE_SECONDS = 4.0
RECONNECT_EVERY_SECONDS = 3.0
TAKEOVER_WAIT_SECONDS = 15  # time for an old dashboard to land and release the port
WATCHDOG_SECONDS = 0.25
LOW_BATTERY_PCT = 20
HOT_TEMP_C = 80
MAX_TILT_DEG = 10
REFUSAL_HINT = (
    "Fixes to try: 1) IMU calibration in the Tello phone app (Settings > More > IMU Calibration), "
    "2) turn it off 15 min if hot, 3) flat surface, 4) turn the lights on (its downward camera "
    "needs to see the floor), 5) restart the drone."
)


def flush_replies(tello: Tello) -> None:
    """Drop stray replies so the next command reads its own answer.

    The original Tello firmware sometimes answers "command" twice; without this every later
    reply is shifted by one (e.g. takeoff "fails" with a temperature reading while airborne).
    """
    time.sleep(FLUSH_WAIT_SECONDS)
    tello.get_own_udp_object()["responses"].clear()


def write_log(text: str) -> str:
    """Print and append to the log file, so failures can be read after reconnecting to the internet."""
    line = f"{time.strftime('%H:%M:%S')}  {text}"
    print(text)
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging to disk is best-effort
    return line


class Drone:
    def __init__(self, tello: Tello) -> None:
        self.tello = tello
        self.rc = (0, 0, 0, 0)
        self.rc_at = 0.0
        self.busy = ""
        self.jpeg: bytes | None = None
        self.log: deque[str] = deque(maxlen=30)
        self.state_at = time.time()
        self.frame_at = 0.0
        self.reconnect_at = 0.0

    def start(self) -> None:
        """Connect if the drone is reachable; otherwise keep running and let the watchdog retry."""
        try:
            self.tello.connect()
            flush_replies(self.tello)
            self.note(f"Connected | {self.readings()}")
        except Exception as exc:
            self.state_at = 0.0  # marks us disconnected so the watchdog keeps knocking
            self.note(f"Drone not reachable yet ({exc}). Waiting: connect the laptop to the TELLO Wi-Fi.")
        # Video can take a while (or fail) to start; never let it block telemetry and controls.
        for loop in (self._video_loop, self._rc_loop, self._watchdog):
            threading.Thread(target=loop, daemon=True).start()

    def _video_loop(self) -> None:
        while True:
            while not self.connected:
                time.sleep(1)
            self.note("Starting video...")
            try:
                self.tello.streamon()
                self.frames = self.tello.get_frame_read()
                break
            except Exception as exc:
                self.note(f"Video failed to start ({exc}), retrying...")
                time.sleep(RECONNECT_EVERY_SECONDS)
        self.note("Video started")
        self._encode_loop()

    @property
    def connected(self) -> bool:
        return time.time() - self.state_at < STATE_STALE_SECONDS

    def _watchdog(self) -> None:
        """Notice when the drone stops talking (restart, Wi-Fi switch) and bring it back.

        A restarted Tello forgets SDK mode, so telemetry and video stop until it hears
        "command" and "streamon" again. Without this the page keeps showing frozen data.
        """
        last_state, was_connected = None, self.connected
        while True:
            state = self.tello.get_current_state()
            if state and state is not last_state:  # the receiver thread swaps in a new dict per packet
                last_state, self.state_at = state, time.time()
            connected = self.connected
            if connected != was_connected:
                was_connected = connected
                if connected:
                    self.tello.is_flying = self.tello.get_height() > 0
                    self.note(f"Drone reconnected | {self.readings()}")
                else:
                    self.note("Drone connection LOST (restarted, out of range, or Wi-Fi switched). Reconnecting...")
            video_stale = time.time() - self.frame_at > VIDEO_STALE_SECONDS
            if (not connected or video_stale) and time.time() - self.reconnect_at > RECONNECT_EVERY_SECONDS:
                self.reconnect_at = time.time()
                try:
                    self.tello.send_command_without_return("command")
                    self.tello.send_command_without_return("streamon")
                except OSError:
                    pass  # no network yet; try again next round
            time.sleep(WATCHDOG_SECONDS)

    def note(self, text: str) -> None:
        self.log.appendleft(write_log(text))

    def _encode_loop(self) -> None:
        params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        last_frame = None
        while True:
            try:
                frame = self.frames.frame
                if frame is not None and frame is not last_frame:
                    last_frame = frame
                    self.frame_at = time.time()
                    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), params)
                    if ok:
                        self.jpeg = buf.tobytes()
            except Exception as exc:
                self.note(f"Video error: {exc}")
                time.sleep(1)
            time.sleep(FRAME_SECONDS)

    def _rc_loop(self) -> None:
        while True:
            if self.tello.is_flying and not self.busy:
                fresh = time.time() - self.rc_at < DEADMAN_SECONDS
                try:
                    self.tello.send_rc_control(*(self.rc if fresh else (0, 0, 0, 0)))
                except Exception as exc:
                    self.note(f"Control error: {exc}")
            time.sleep(1 / RC_HZ)

    def set_rc(self, values: dict) -> None:
        def clamp(key: str) -> int:
            return max(-RC_LIMIT, min(RC_LIMIT, int(values.get(key, 0))))

        self.rc = (clamp("lr"), clamp("fb"), clamp("ud"), clamp("yaw"))
        self.rc_at = time.time()

    def action(self, name: str) -> str:
        if name == "emergency":
            self.tello.emergency()
            self.tello.is_flying = False
            self.note("EMERGENCY STOP: motors cut")
            return "ok"
        if self.busy:
            return f"busy ({self.busy})"
        # Land is always allowed: if our flying flag is ever wrong, landing must still work.
        if name == "takeoff" and self.tello.is_flying:
            return "already flying"
        if name == "takeoff" and not self.connected:
            return "drone not connected (no telemetry), waiting to reconnect"
        threading.Thread(target=self._run_action, args=(name,), daemon=True).start()
        return "ok"

    def _run_action(self, name: str) -> None:
        self.busy = name
        self.note(f"{name.capitalize()}...")
        try:
            flush_replies(self.tello)
            if name == "takeoff":
                self._takeoff()
            else:
                self.tello.land()
                self.note("Land done")
        except Exception as exc:
            self.note(f"{name.capitalize()} failed: {exc} | {self.readings()}")
        finally:
            self.busy = ""

    def readings(self) -> str:
        v = self.value
        return (f"battery {v('get_battery')}%, temp {v('get_lowest_temperature')}-{v('get_highest_temperature')}C, "
                f"pitch {v('get_pitch')} roll {v('get_roll')}, floor sensor {v('get_distance_tof')}cm")

    def preflight_problems(self) -> list[str]:
        t = self.tello
        problems = []
        if t.get_battery() < LOW_BATTERY_PCT:
            problems.append(f"battery {t.get_battery()}% is too low, charge it")
        if t.get_highest_temperature() >= HOT_TEMP_C:
            problems.append(f"drone is {t.get_highest_temperature()}C, turn it off for 15 min to cool")
        if max(abs(t.get_pitch()), abs(t.get_roll())) > MAX_TILT_DEG:
            problems.append("drone is tilted, put it on a flat surface")
        return problems

    def _takeoff(self) -> None:
        problems = self.preflight_problems()
        if problems:
            self.note("Take off blocked: " + "; ".join(problems))
            return
        # One raw attempt (no silent retries) so we log the drone's exact reply.
        reply = self.tello.send_command_with_return("takeoff", timeout=TAKEOFF_TIMEOUT)
        if reply.strip().lower() == "ok":
            self.tello.is_flying = True
            self.note("Takeoff done")
            return
        self.note(f"Drone refused takeoff: '{reply}' | {self.readings()}")
        self.note(REFUSAL_HINT)

    def status(self) -> dict:
        # Before the first connection there is no telemetry yet; report zeros instead of erroring.
        v = self.value
        return {
            "battery": v("get_battery"),
            "temp": v("get_highest_temperature"),
            "height": v("get_height"),
            "tof": v("get_distance_tof"),
            "flight_time": v("get_flight_time"),
            "speed": [v("get_speed_x"), v("get_speed_y"), v("get_speed_z")],
            "attitude": [v("get_pitch"), v("get_roll"), v("get_yaw")],
            "flying": self.tello.is_flying,
            "connected": self.connected,
            "state_age": round(time.time() - self.state_at, 1) if self.state_at else 999,
            "video_age": round(time.time() - self.frame_at, 1) if self.frame_at else None,
            "busy": self.busy,
            "log": list(self.log),
        }

    def value(self, getter: str) -> int:
        try:
            return int(getattr(self.tello, getter)())
        except Exception:
            return 0

    def shutdown(self) -> None:
        if self.tello.is_flying:
            self.note("Landing before exit")
            self.tello.send_rc_control(0, 0, 0, 0)
            self.tello.land()
        self.tello.streamoff()
        self.tello.end()


class DashboardServer(ThreadingHTTPServer):
    # Windows lets a second process share a port when SO_REUSEADDR is set; refuse instead,
    # so a forgotten dashboard can't silently fight a new one for the drone.
    allow_reuse_address = False
    daemon_threads = True


def make_handler(drone: Drone):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console readable
            pass

        def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict, code: int = 200) -> None:
            self._send(json.dumps(data).encode(), "application/json", code)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/status":
                try:
                    self._json(drone.status())
                except Exception as exc:
                    self._json({"error": str(exc)}, 503)
            elif self.path.startswith("/video"):
                self._stream_video()
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = min(int(self.headers.get("Content-Length", 0)), 1024)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if self.path == "/rc":
                drone.set_rc(body)
                return self._json({"result": "ok"})
            if self.path == "/shutdown":  # a newer dashboard is taking over (localhost only)
                self._json({"result": "ok"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            name = self.path.removeprefix("/action/")
            if name in ACTIONS:
                return self._json({"result": drone.action(name)})
            self._json({"error": "not found"}, 404)

        def _stream_video(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    jpeg = drone.jpeg
                    if jpeg:
                        head = f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
                        self.wfile.write(head.encode() + jpeg + b"\r\n")
                    time.sleep(FRAME_SECONDS)
            except OSError:
                return  # browser closed the stream

    return Handler


def bind_server() -> DashboardServer | None:
    """Take the port. If an older dashboard holds it, ask that one to land and exit first."""
    try:
        return DashboardServer((HOST, PORT), make_handler(None))
    except OSError:
        pass
    write_log("Another dashboard is running; asking it to shut down...")
    try:
        req = urllib.request.Request(f"http://{HOST}:{PORT}/shutdown", data=b"{}", method="POST")
        urllib.request.urlopen(req, timeout=3).read()
    except OSError:
        pass  # older versions have no /shutdown; fall through to the retry and message
    deadline = time.time() + TAKEOVER_WAIT_SECONDS
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            return DashboardServer((HOST, PORT), make_handler(None))
        except OSError:
            continue
    return None


def main() -> None:
    write_log("Dashboard starting")
    server = bind_server()
    if server is None:
        write_log(f"An older dashboard is STILL RUNNING on port {PORT} and would not close.")
        print("Close the other black 'Tello dashboard' window (or end python.exe in Task Manager), "
              "then try again.")
        return
    drone = Drone(Tello())
    write_log("Connecting to the drone...")
    drone.start()
    server.RequestHandlerClass = make_handler(drone)
    url = f"http://{HOST}:{PORT}"
    print(f"Dashboard running at {url}  (press Ctrl+C here to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        drone.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        write_log("CRASH: " + traceback.format_exc())
        raise
