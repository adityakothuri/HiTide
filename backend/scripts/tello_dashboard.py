"""Unified Tello dashboard: live video, telemetry, and keyboard/mouse flight control in a browser.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello dashboard" on the Desktop.
It opens http://127.0.0.1:8765 in your browser. Works offline. Press Ctrl+C in the console to stop
(the drone lands first if it is flying).
"""

import json
import threading
import time
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


def flush_replies(tello: Tello) -> None:
    """Drop stray replies so the next command reads its own answer.

    The original Tello firmware sometimes answers "command" twice; without this every later
    reply is shifted by one (e.g. takeoff "fails" with a temperature reading while airborne).
    """
    time.sleep(FLUSH_WAIT_SECONDS)
    tello.get_own_udp_object()["responses"].clear()


class Drone:
    def __init__(self, tello: Tello) -> None:
        self.tello = tello
        self.rc = (0, 0, 0, 0)
        self.rc_at = 0.0
        self.busy = ""
        self.jpeg: bytes | None = None
        self.log: deque[str] = deque(maxlen=30)

    def start(self) -> None:
        self.tello.connect()
        flush_replies(self.tello)
        self.note(f"Connected, battery {self.tello.get_battery()}%")
        # Video can take a while (or fail) to start; never let it block telemetry and controls.
        for loop in (self._video_loop, self._rc_loop):
            threading.Thread(target=loop, daemon=True).start()

    def _video_loop(self) -> None:
        self.note("Starting video...")
        try:
            self.tello.streamon()
            self.frames = self.tello.get_frame_read()
        except Exception as exc:
            self.note(f"Video failed to start: {exc}")
            return
        self.note("Video started")
        self._encode_loop()

    def note(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        self.log.appendleft(line)
        print(text)
        try:
            LOG_FILE.parent.mkdir(exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # logging to disk is best-effort

    def _encode_loop(self) -> None:
        params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        while True:
            try:
                frame = self.frames.frame
                if frame is not None:
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
        threading.Thread(target=self._run_action, args=(name,), daemon=True).start()
        return "ok"

    def _run_action(self, name: str) -> None:
        self.busy = name
        self.note(f"{name.capitalize()}...")
        try:
            flush_replies(self.tello)
            getattr(self.tello, name)()
            self.note(f"{name.capitalize()} done")
        except Exception as exc:
            self.note(f"{name.capitalize()} failed: {exc}")
        finally:
            self.busy = ""

    def status(self) -> dict:
        t = self.tello
        return {
            "battery": t.get_battery(),
            "temp": t.get_highest_temperature(),
            "height": t.get_height(),
            "tof": t.get_distance_tof(),
            "flight_time": t.get_flight_time(),
            "speed": [t.get_speed_x(), t.get_speed_y(), t.get_speed_z()],
            "attitude": [t.get_pitch(), t.get_roll(), t.get_yaw()],
            "flying": t.is_flying,
            "busy": self.busy,
            "log": list(self.log),
        }

    def shutdown(self) -> None:
        if self.tello.is_flying:
            self.note("Landing before exit")
            self.tello.send_rc_control(0, 0, 0, 0)
            self.tello.land()
        self.tello.streamoff()
        self.tello.end()


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


def main() -> None:
    drone = Drone(Tello())
    print("Connecting to the drone...")
    drone.start()
    server = ThreadingHTTPServer((HOST, PORT), make_handler(drone))
    server.daemon_threads = True
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
    main()
