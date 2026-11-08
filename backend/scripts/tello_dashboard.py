"""Unified Tello dashboard: live video, telemetry, and keyboard/mouse flight control in a browser.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello dashboard" on the Desktop.
It opens http://127.0.0.1:8765 in your browser. Works offline. Press Ctrl+C in the console to stop
(the drone lands first if it is flying).
"""

import json
import math
import os
import re
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import cv2
import numpy as np
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
LAND_RESEND_SECONDS = 1.5  # keep repeating "land" until the drone is down (works mid-takeoff too)
LAND_MIN_SENDS = 3
LAND_TIMEOUT_SECONDS = 15
DRIFT_SPEED = 3  # Tello speed units; average above this while hovering hands-off = drifting
WOBBLE_DEG = 4  # pitch/roll swing (max - min) above this while hovering hands-off = wobbling
HOVER_WINDOW_SECONDS = 3.0
HOVER_REPORT_EVERY = 8.0
RC_STEP = 8  # max change per control tick (20 Hz): 0 -> 50 in ~0.3 s, so key presses don't jerk it
NORMAL_DRAIN_PCT_PER_MIN = 8  # a healthy Tello hovers ~13 min on a full battery
HIGH_DRAIN_FACTOR = 2
MIN_FLIGHT_FOR_DRAIN_S = 10
TAKEOVER_WAIT_SECONDS = 15  # time for an old dashboard to land and release the port
WATCHDOG_SECONDS = 0.25
LOW_BATTERY_PCT = 20
# Battery restrictions (low-battery takeoff block, worn-battery takeoff margin, auto-land before lift loss,
# gentle inputs) are OFF for now. Set TELLO_BATTERY_GUARD=1 to turn them back on.
BATTERY_GUARD = os.environ.get("TELLO_BATTERY_GUARD", "0") == "1"
HOT_TEMP_C = 80  # the drone refuses takeoff around here
WARM_TEMP_C = 70  # warn while it sits powered on: Tellos only cool when flying
WARM_REPORT_EVERY = 120.0
RECORD_EVERY_SECONDS = 1.0  # flight recorder: one telemetry row per second while flying
SINK_CM = 25  # height lost without an "down" input over SINK_WINDOW_SECONDS = uncommanded descent
SINK_WINDOW_SECONDS = 3.0
SINK_REPORT_EVERY = 10.0
SAG_BATTERY_PCT = 35  # below this, a worn battery's voltage can dip under the auto-land limit
PROFILE_FILE = LOG_FILE.parent / "battery_profile.json"  # where this battery lost lift; delete after a swap
LIFT_MARGIN_PCT = 4  # auto-land this far above the level where the battery last lost lift
TAKEOFF_RESERVE_SECONDS = 60  # refuse takeoff with less flight than this above that level
WORN_RC_LIMIT = 30  # gentler inputs on a worn battery: current spikes are what collapse it
WORN_RC_STEP = 4
GROUND_FLOOR_CM = 15  # floor sensor reads ~10 cm when sitting on the ground
GROUNDED_SECONDS = 2.0  # "flying" but on the floor this long = lost lift; land to stop the motors
DRAIN_SETTLE_SECONDS = 5.0  # battery % reads low under load; read it after it recovers
MAX_TILT_DEG = 6  # take off only from a flat floor: a tilted or raised start makes it lurch and drift
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


RUN_DIR: Path | None = None
_journal_lock = threading.Lock()


def record_event(event: str, *, frame=None, overlay=None, **fields) -> None:
    """Append one timestamped event and its associated images to this run."""
    if RUN_DIR is None:
        return
    try:
        with _journal_lock:
            stamp = time.time_ns()
            row = {"time_ns": stamp, "event": event, **fields}
            for label, image in (("frame", frame), ("overlay", overlay)):
                if image is None:
                    continue
                filename = f"{stamp}_{label}.jpg"
                try:
                    content = image if isinstance(image, bytes) else encode_jpeg(image)
                    if content is None:
                        raise ValueError("JPEG encoding failed")
                    (RUN_DIR / filename).write_bytes(content)
                    row[label] = filename
                except (OSError, ValueError, cv2.error) as exc:
                    row[label + "_error"] = str(exc)
            with (RUN_DIR / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, allow_nan=False) + "\n")
    except (OSError, ValueError, TypeError) as exc:
        print(f"Run log write failed: {exc}", file=sys.stderr)


def record_telemetry(drone, done: threading.Event) -> None:
    while not done.is_set():
        try:
            state = drone.status()
            state.pop("log", None)
            record_event("telemetry", **state, requested_rc=drone.rc, applied_rc=drone.rc_out)
        except Exception as exc:
            record_event("telemetry_error", reason=str(exc))
        done.wait(1.0)


def write_log(text: str) -> str:
    """Print and append to the log file, so failures can be read after reconnecting to the internet."""
    line = f"{time.strftime('%H:%M:%S')}  {text}"
    record_event("message", text=text)
    print(text)
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging to disk is best-effort
    return line


def load_profile() -> dict:
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_profile(profile: dict) -> None:
    try:
        PROFILE_FILE.parent.mkdir(exist_ok=True)
        PROFILE_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except OSError:
        pass  # best-effort; the in-memory profile still protects this session


# ---------- gauge tray water level (docs/gauge-water-level-plan.md, "Integration") ----------

_HERE = Path(__file__).resolve().parent
# The `gauge` package: next to this file in the standalone demo build, else backend/ in the repo.
BACKEND_DIR = _HERE if (_HERE / "gauge").is_dir() else _HERE.parent
GAUGE_HZ = 2
GAUGE_DYE_DEFAULT = "blue"
GAUGE_LOADING = "loading the gauge model"
GAUGE_LOADING_RETRY = "loading the gauge model, try again in a moment"
MAX_CORNER_PX = 4096  # sanity bound for clicked corner coordinates
GAUGE_PRESS_WAIT_SECONDS = 1.5  # a press waits this long for a load it started itself, then answers
GAUGE_ERROR_WAIT_SECONDS = 1.0  # back off after a reader error so a bad frame can't spin the CPU
GAUGE_ENCODE_ERROR = "Overlay error: JPEG encode failed"
ESTIMATE_FIELDS = (
    "level_mm", "level_mm_range", "ft", "ft_range", "confidence", "crossing_flooded", "car_level",
    "houses_flooded", "houses_total", "visible_cells", "wet_cells", "wet_fraction", "tags_seen",
    "reproj_err_px", "has_baseline", "baseline_moved", "simulated", "reason", "ts", "pose_source", "depths",
)


class GaugeReaderLike(Protocol):
    """The slice of gauge.water.GaugeReader the bridge uses."""

    def set_baseline(self, frame: np.ndarray) -> tuple[bool, str]: ...
    def update(self, frame: np.ndarray) -> Any: ...
    def overlay(self, frame: np.ndarray, estimate: Any) -> np.ndarray: ...


def default_gauge_reader() -> GaugeReaderLike:
    """Import backend/gauge lazily, so a missing or broken package never stops the dashboard."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from gauge.water import GaugeReader

    from gauge.camera import load_intrinsics
    from gauge.model import load_tray

    dye = os.environ.get("GAUGE_DYE", GAUGE_DYE_DEFAULT)
    # The demo always places the tray with its FLOOD WATCH edge towards the drone, so the outline is found
    # automatically. GAUGE_TRAY_FACING=any lets the terrain decide instead (may ask for corner clicks).
    facing = os.environ.get("GAUGE_TRAY_FACING", "flood_watch")
    return GaugeReader(load_tray(), load_intrinsics(), dye=dye, facing=None if facing == "any" else facing)


def encode_jpeg(frame_bgr: np.ndarray) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def rgb_to_bgr(frame_rgb: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(frame_rgb[:, :, ::-1])


def jsonable(value: Any) -> Any:
    """numpy scalars and tuples from the estimate -> plain JSON types; NaN and inf -> None."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # json.dumps would write NaN, which JSON.parse in the browser rejects
    return value


class GaugeService:
    """Reads the gauge tray water level from the latest frame at about GAUGE_HZ while enabled.

    Runs on its own thread and touches the drone only through `frame_source`, so a slow or
    failing reader can never stall telemetry or flight control. Reader errors are logged once
    per distinct message and reported in status()["error"]. The model loads on a background
    thread, and button presses never wait on a load that is already running.
    """

    def __init__(self, frame_source: Callable[[], np.ndarray | None], note: Callable[[str], None],
                 reader_factory: Callable[[], GaugeReaderLike] = default_gauge_reader,
                 encoder: Callable[[np.ndarray], bytes | None] = encode_jpeg,
                 interval: float = 1 / GAUGE_HZ, geometry_sink=None) -> None:
        self._frame_source = frame_source  # RGB frames, as djitellopy delivers them
        self._note = note
        self._geometry_sink = geometry_sink
        self._reader_factory = reader_factory
        self._encoder = encoder
        self._interval = interval
        self._reader: GaugeReaderLike | None = None
        self._unavailable = ""  # why the gauge package could not load
        self._state_lock = threading.Lock()  # enabled, the loop thread and load state change together
        self._reader_lock = threading.Lock()  # baseline and update never run at the same time
        self._thread: threading.Thread | None = None
        self._loading = False
        self._load_done = threading.Event()
        self.enabled = False
        self.has_baseline = False
        self.corners: list[list[float]] | None = None  # clicked tray corners (frame px), tag-free pose
        self.geometry: dict[str, Any] = {}
        self.estimate: dict[str, Any] = {}
        self.overlay_jpeg: bytes | None = None
        self.error: str | None = None

    # ----- model loading -----

    def _begin_load(self, retry: bool) -> tuple[threading.Event | None, bool]:
        """(event set when the load finishes, or None if there is nothing to wait for; True if this call started it).

        `retry` (a button press) tries again after a failure, e.g. once the package is fixed.
        """
        with self._state_lock:
            if self._reader is not None:
                return None, False
            if self._loading:
                return self._load_done, False
            if self._unavailable and not retry:
                return None, False
            self._loading = True
            self._load_done = threading.Event()
            done = self._load_done
        threading.Thread(target=self._load, args=(done,), daemon=True).start()
        return done, True

    def _load(self, done: threading.Event) -> None:
        """Runs without holding any lock, so status polls and presses answer while the model loads."""
        reader, problem = None, ""
        try:
            reader = self._reader_factory()
        except Exception as exc:  # noqa: BLE001 - ImportError, missing tray data, bad camera json
            problem = f"{type(exc).__name__}: {exc}"
        with self._state_lock:
            if problem:
                self.error = problem
            elif self.error == self._unavailable:
                self.error = None  # an earlier failed load no longer applies
            self._reader, self._unavailable, self._loading = reader, problem, False
        self._note("Water gauge ready" if reader else f"Water gauge unavailable ({problem})")
        done.set()

    def _ensure_reader(self, retry: bool = False, timeout: float | None = None) -> GaugeReaderLike | None:
        """Load if needed and wait up to `timeout` seconds (None = until done)."""
        done, _ = self._begin_load(retry)
        if done is not None:
            done.wait(timeout)
        return self._reader

    def preload(self) -> None:
        """Load the gauge model in the background so the first status poll answers at once."""
        self._begin_load(retry=False)

    def _reader_for_press(self) -> tuple[GaugeReaderLike | None, str]:
        """(reader, "") or (None, why not). Answers at once while a load is already running."""
        done, started = self._begin_load(retry=True)
        if done is not None and not (started and done.wait(GAUGE_PRESS_WAIT_SECONDS)):
            return None, GAUGE_LOADING_RETRY
        if self._reader is None:
            return None, f"gauge unavailable: {self._unavailable}"
        return self._reader, ""

    # ----- button presses -----

    def _frame_bgr(self) -> np.ndarray | None:
        frame = self._frame_source()
        return None if frame is None else rgb_to_bgr(frame)

    def capture_baseline(self) -> str:
        reader, problem = self._reader_for_press()
        if reader is None:
            return problem
        frame = self._frame_bgr()
        if frame is None:
            return "no video frame yet"
        try:
            with self._reader_lock:
                ok, reason = reader.set_baseline(frame)
        except Exception as exc:  # noqa: BLE001 - contain reader faults
            record_event("baseline_error", frame=frame, reason=str(exc))
            return self._record_error("Baseline", exc)
        record_event("baseline", frame=frame, accepted=bool(ok), reason=str(reason), corners=self.corners)
        self.has_baseline = self.has_baseline or bool(ok)
        self._note("Water gauge: dry baseline captured" if ok else f"Water gauge baseline refused: {reason}")
        return "ok" if ok else str(reason)

    def set_corners(self, points: Any) -> str:
        """Use 4 clicked tray corners for the pose (or clear them with points=None)."""
        reader, problem = self._reader_for_press()
        if reader is None:
            return problem
        setter, clearer = getattr(reader, "set_corners", None), getattr(reader, "clear_corners", None)
        if setter is None or clearer is None:
            return "this gauge version can't use tray corners"
        try:
            with self._reader_lock:
                if points is None:
                    clearer()
                    ok, reason = True, "ok"
                else:
                    ok, reason = setter(points)
        except Exception as exc:  # noqa: BLE001 - contain reader faults
            return self._record_error("Tray corners", exc)
        if ok:
            self.corners = None if points is None else [[float(x), float(y)] for x, y in points]
            self._note("Water gauge: tray corners cleared" if points is None else "Water gauge: tray corners set")
        return "ok" if ok else str(reason)

    def start(self) -> str:
        reader, problem = self._reader_for_press()
        if reader is None:
            return problem
        with self._state_lock:
            self.enabled = True
            started = self._thread is None  # a loop that still holds _thread will see enabled=True
            if started:
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
        if started:
            self._note("Water gauge reading started")
        return "ok"

    def stop(self) -> str:
        with self._state_lock:
            was_enabled, self.enabled = self.enabled, False
        if was_enabled:
            self._note("Water gauge reading stopped")
        return "ok"

    # ----- reading -----

    def _keep_running(self) -> bool:
        """The loop's exit check. Under the lock, so start() never mistakes an exiting loop for a live one."""
        with self._state_lock:
            if self.enabled:
                return True
            if self._thread is threading.current_thread():
                self._thread = None
            return False

    def _loop(self) -> None:
        last_frame = None
        while self._keep_running():
            frame = self._frame_source()
            if frame is None or frame is last_frame:
                time.sleep(self._interval)
                continue
            last_frame = frame
            self.read_once(rgb_to_bgr(frame))
            time.sleep(self._interval if self.error is None else GAUGE_ERROR_WAIT_SECONDS)

    def read_once(self, frame_bgr: np.ndarray) -> None:
        """One reading: smoothed estimate plus the annotated overlay. Never raises.

        On a reader error the last estimate stays; its age_s in status() makes it visibly stale.
        """
        reader = self._reader
        if reader is None:
            return
        try:
            with self._reader_lock:
                estimate = reader.update(frame_bgr)
                overlay = reader.overlay(frame_bgr, estimate)
                geometry_reader = getattr(reader, "scene_geometry", None)
                geometry = geometry_reader(frame_bgr) if geometry_reader else {}
            data = jsonable(estimate.to_dict())
            jpeg = self._encoder(overlay)
        except Exception as exc:  # noqa: BLE001 - contain reader faults
            record_event("reading_error", frame=frame_bgr, reason=str(exc))
            self._record_error("Reader", exc)
            return
        record_event("reading", frame=frame_bgr, overlay=jpeg, estimate=data, corners=self.corners)
        if self._geometry_sink and data.get("ft") is not None and not data.get("reason"):
            self._geometry_sink(frame_bgr, geometry)
        self.geometry = jsonable(geometry)
        self.estimate = data
        self.overlay_jpeg = jpeg  # None on an encode failure: never pair an old overlay with a new estimate
        if jpeg is None:
            self._record_message(GAUGE_ENCODE_ERROR)
        else:
            self.error = None

    def _record_error(self, what: str, exc: Exception) -> str:
        return self._record_message(f"{what} error: {type(exc).__name__}: {exc}")

    def _record_message(self, message: str) -> str:
        if message != self.error:  # log once per distinct error, not twice a second
            self._note(f"Water gauge {message}")
        self.error = message
        return message

    @property
    def running(self) -> bool:
        thread = self._thread
        return self.enabled and thread is not None and thread.is_alive()

    def status(self) -> dict[str, Any]:
        """Never blocks on loading: while the model loads, report unavailable with that reason."""
        loading = self._reader is None and not self._unavailable
        if loading:
            self.preload()
        estimate = {k: self.estimate.get(k) for k in ESTIMATE_FIELDS}
        estimate["has_baseline"] = bool(estimate["has_baseline"] or self.has_baseline)
        ts = estimate["ts"]
        fresh_ts = isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0
        return {
            "scene": self.geometry,
            "gauge": "online" if self._reader is not None else "unavailable",
            "enabled": self.enabled,
            "running": self.running,
            "error": self.error or (GAUGE_LOADING if loading else None),
            "age_s": round(max(0.0, time.time() - ts), 1) if fresh_ts else None,
            "corners": self.corners,
            **estimate,
        }


class Drone:
    def __init__(self, tello: Tello) -> None:
        self.tello = tello
        self.rc = (0, 0, 0, 0)
        self.rc_at = 0.0
        self.busy = ""  # "takeoff" while a takeoff is in progress
        self.landing = False  # separate from busy: landing must be able to interrupt a takeoff
        self.jpeg: bytes | None = None
        self.log: deque[str] = deque(maxlen=30)
        self.state_at = time.time()
        self.frame_at = 0.0
        self.reconnect_at = 0.0
        self.hover_samples: deque[tuple[float, int, int, int]] = deque()
        self.hover_reported = 0.0
        self.hover_steady_noted = False
        self.rc_out = (0, 0, 0, 0)  # what we actually send: ramps toward self.rc
        self.flight_start: tuple[float, int] | None = None  # (time, battery %) at takeoff
        self.wobbled = False  # this flight; tells a worn battery apart from a mechanical fault
        self.warm_reported = 0.0
        self.recorded_at = 0.0
        self.record_file: Path | None = None
        self.heights: deque[tuple[float, int]] = deque()
        self.sink_reported = 0.0
        self.grounded_since = 0.0
        self.profile = load_profile()  # {"lift_loss_pct", "drain_pct_per_min", "updated"}

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
            if connected:
                self._check_hover()
                self._check_idle_heat()
                self._record_flight()
                self._check_sink()
                self._check_grounded_motors_on()
                self._check_lift_reserve()
            time.sleep(WATCHDOG_SECONDS)

    def _check_hover(self) -> None:
        """While hovering hands-off, measure whether it wobbles (tilts) or drifts (slides).

        They have different causes. Wobble is mechanical: a chipped or swapped propeller, a
        weak motor, or a loose guard makes the flight controller fight to stay level. Drift
        is the downward camera (VPS) not seeing the floor: dim light, plain or shiny floor.
        """
        holding = (self.tello.is_flying and not self.busy and not self.landing
                   and (self.rc == (0, 0, 0, 0) or time.time() - self.rc_at > DEADMAN_SECONDS))
        if not holding:
            self.hover_samples.clear()
            return
        now = time.time()
        v = self.value
        speed = max(abs(v("get_speed_x")), abs(v("get_speed_y")))
        self.hover_samples.append((now, v("get_pitch"), v("get_roll"), speed))
        while self.hover_samples and now - self.hover_samples[0][0] > HOVER_WINDOW_SECONDS:
            self.hover_samples.popleft()
        span = now - self.hover_samples[0][0]
        if span < HOVER_WINDOW_SECONDS * 0.6 or now - self.hover_reported < HOVER_REPORT_EVERY:
            return
        pitches = [p for _, p, _, _ in self.hover_samples]
        rolls = [r for _, _, r, _ in self.hover_samples]
        swing = max(max(pitches) - min(pitches), max(rolls) - min(rolls))
        drift = sum(sp for *_, sp in self.hover_samples) / len(self.hover_samples)
        self.hover_reported = now
        if swing > WOBBLE_DEG:
            self.wobbled = True
            self.note(f"WOBBLING while hovering (tilt swings {swing} deg). That's mechanical: check each "
                      "propeller for chips and the right A/B motor, spin each motor by hand for grit or hair, "
                      "seat the prop guards, push the battery fully in. A corner that sounds different is a weak motor.")
        if drift > DRIFT_SPEED:
            self.note(f"DRIFTING while hovering (speed {drift:.0f}, floor {v('get_distance_tof')}cm). Its "
                      "downward camera can't see the floor: bright lights, a patterned rug or tape marks, "
                      "0.5-2 m up, no shiny or plain floors.")
        if swing <= WOBBLE_DEG and drift <= DRIFT_SPEED and not self.hover_steady_noted:
            self.hover_steady_noted = True
            self.note(f"Hover steady (tilt swing {swing} deg, drift {drift:.0f}).")

    def _record_flight(self) -> None:
        """One CSV row per second from the start of takeoff (when drift begins) until landed."""
        if not (self.tello.is_flying or self.busy == "takeoff" or self.landing):
            self.record_file = None
            return
        now = time.time()
        if now - self.recorded_at < RECORD_EVERY_SECONDS:
            return
        self.recorded_at = now
        v = self.value
        try:
            if self.record_file is None:
                self.record_file = LOG_FILE.parent / f"flight_{time.strftime('%Y%m%d_%H%M%S')}.csv"
                self.record_file.write_text("time,height_cm,floor_cm,battery_pct,temp_c,pitch,roll,"
                                            "speed_x,speed_y,input_lr,input_fb,input_ud,input_yaw\n", encoding="utf-8")
            row = [time.strftime("%H:%M:%S"), v("get_height"), v("get_distance_tof"), v("get_battery"),
                   v("get_highest_temperature"), v("get_pitch"), v("get_roll"), v("get_speed_x"),
                   v("get_speed_y"), *self.rc_out]
            with self.record_file.open("a", encoding="utf-8") as f:
                f.write(",".join(map(str, row)) + "\n")
        except OSError:
            pass  # recording is best-effort

    def _check_sink(self) -> None:
        """Spot the drone losing height when nobody pressed down, and say why it probably is."""
        if not self.tello.is_flying or self.busy or self.landing:
            self.heights.clear()
            return
        now = time.time()
        self.heights.append((now, self.value("get_height")))
        while self.heights and now - self.heights[0][0] > SINK_WINDOW_SECONDS:
            self.heights.popleft()
        commanded_down = self.rc_out[2] < 0 or self.rc[2] < 0
        drop = max(h for _, h in self.heights) - self.heights[-1][1]
        if commanded_down or drop < SINK_CM or now - self.sink_reported < SINK_REPORT_EVERY:
            return
        self.sink_reported = now
        battery, temp = self.value("get_battery"), self.value("get_highest_temperature")
        if temp >= HOT_TEMP_C:
            why = "it is overheating and protecting itself. Land and let it cool."
        elif battery <= SAG_BATTERY_PCT or self._draining_fast(battery):
            self._remember_lift_loss(battery)
            why = ("the battery can't supply enough power under load, so all four motors lose lift at once "
                   "(the drop is level, not tipped). Typical of a worn battery even at 40-60%. Use a fresh, full battery.")
        else:
            why = ("its height sensor is confused (flying over a table edge, a step, or a dark/shiny floor). "
                   "Fly over flat, matte, well-lit floor.")
        self.note(f"DESCENDING ON ITS OWN ({drop}cm in {SINK_WINDOW_SECONDS:.0f}s, no down input) at battery "
                  f"{battery}%, {temp}C. Likely: {why} Press L rather than Kill so it lands instead of dropping.")

    @property
    def worn(self) -> bool:
        """Worn-battery protections apply only with BATTERY_GUARD on (the profile is kept either way)."""
        return BATTERY_GUARD and "lift_loss_pct" in self.profile

    def _remember_lift_loss(self, battery: int) -> None:
        self.profile = {**self.profile, "lift_loss_pct": battery, "updated": time.strftime("%Y-%m-%d %H:%M")}
        save_profile(self.profile)
        self.note(f"Saved: this battery loses lift around {battery}%. Future flights land automatically at "
                  f"{battery + LIFT_MARGIN_PCT}%. After swapping in a new battery, delete {PROFILE_FILE}.")

    def _land_floor_pct(self) -> int:
        return int(self.profile["lift_loss_pct"]) + LIFT_MARGIN_PCT

    def _drain_per_second(self) -> float:
        """Measured this flight if possible, else this battery's last known rate."""
        if self.flight_start:
            started, start_battery = self.flight_start
            elapsed = time.time() - started
            used = start_battery - self.value("get_battery")
            if elapsed > 5 and used > 0:
                return used / elapsed
        return float(self.profile.get("drain_pct_per_min", NORMAL_DRAIN_PCT_PER_MIN)) / 60

    def lift_left_seconds(self) -> int | None:
        """Seconds of flight before the battery reaches its auto-land level; None if unknown."""
        if not self.worn or not self.tello.is_flying:
            return None
        rate = self._drain_per_second()
        return max(0, int((self.value("get_battery") - self._land_floor_pct()) / rate)) if rate > 0 else None

    def _check_lift_reserve(self) -> None:
        """Land on purpose before the worn battery collapses and drops the drone."""
        if not self.worn or not self.tello.is_flying or self.busy or self.landing:
            return
        battery = self.value("get_battery")
        if battery > self._land_floor_pct():
            return
        self.note(f"Battery {battery}%: landing now, before it reaches {self.profile['lift_loss_pct']}% "
                  "where this battery loses lift.")
        self.action("land")

    def _draining_fast(self, battery: int) -> bool:
        """Battery use since takeoff well above normal: a worn battery that will sag and lose lift."""
        if not self.flight_start:
            return False
        started, start_battery = self.flight_start
        minutes = (time.time() - started) / 60
        return minutes > 0 and (start_battery - battery) / minutes > NORMAL_DRAIN_PCT_PER_MIN * HIGH_DRAIN_FACTOR

    def _check_grounded_motors_on(self) -> None:
        """A drone that lost lift sits on the floor with its motors still running. Land it to stop them."""
        on_floor = (self.tello.is_flying and not self.busy and not self.landing and self.rc[2] <= 0
                    and self.value("get_distance_tof") <= GROUND_FLOOR_CM)
        if not on_floor:
            self.grounded_since = 0.0
            return
        self.grounded_since = self.grounded_since or time.time()
        if time.time() - self.grounded_since < GROUNDED_SECONDS:
            return
        self.grounded_since = 0.0
        self.note(f"On the floor with motors still running (lost lift at battery {self.value('get_battery')}%). "
                  "Landing to stop the motors.")
        self.action("land")

    def _check_idle_heat(self) -> None:
        temp = self.value("get_highest_temperature")
        if self.tello.is_flying or temp < WARM_TEMP_C or time.time() - self.warm_reported < WARM_REPORT_EVERY:
            return
        self.warm_reported = time.time()
        self.note(f"Drone is {temp}C sitting on the ground. Tellos only cool while flying, and it refuses takeoff "
                  f"at {HOT_TEMP_C}C. Turn it off between flights (or fly now if you're about to).")

    def _note_battery_drain(self, landed_at: float) -> None:
        """Called a few seconds after landing, once the battery reading has recovered from load sag."""
        if not self.flight_start:
            return
        started, battery = self.flight_start
        self.flight_start = None
        seconds = landed_at - started
        used = battery - self.value("get_battery")
        if seconds < MIN_FLIGHT_FOR_DRAIN_S or used <= 0:
            return
        rate = used / seconds * 60
        self.profile = {**self.profile, "drain_pct_per_min": round(rate, 1)}
        save_profile(self.profile)
        if rate <= NORMAL_DRAIN_PCT_PER_MIN * HIGH_DRAIN_FACTOR:
            verdict = "normal"
        elif self.wobbled:
            verdict = "HIGH, and it wobbled: likely a damaged or swapped propeller or a weak motor"
        else:
            verdict = "HIGH with a steady hover: likely a worn battery, expect short flights"
        minutes_left = self.value("get_battery") / rate if rate else 0
        self.note(f"Flight used {used}% battery in {seconds:.0f}s ({rate:.0f}%/min, {verdict}). "
                  f"About {minutes_left:.1f} min of flight left at this rate.")

    def note(self, text: str) -> None:
        self.log.appendleft(write_log(text))

    def latest_frame(self) -> np.ndarray | None:
        """The newest RGB camera frame, or None before video starts."""
        frames = getattr(self, "frames", None)  # set by _video_loop once the stream is up
        return None if frames is None else frames.frame

    def _encode_loop(self) -> None:
        params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        last_frame = None
        while True:
            try:
                frame = self.frames.frame
                if frame is not None and frame is not last_frame:
                    last_frame = frame
                    self.frame_at = time.time()
                    renderer = getattr(self, "live_overlay", None)
                    image = renderer.render(frame) if renderer else cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    ok, buf = cv2.imencode(".jpg", image, params)
                    if ok:
                        self.jpeg = buf.tobytes()
            except Exception as exc:
                self.note(f"Video error: {exc}")
                time.sleep(1)
            time.sleep(FRAME_SECONDS)

    def _rc_loop(self) -> None:
        while True:
            if self.tello.is_flying and not self.busy and not self.landing:
                fresh = time.time() - self.rc_at < DEADMAN_SECONDS
                limit, step = (WORN_RC_LIMIT, WORN_RC_STEP) if self.worn else (RC_LIMIT, RC_STEP)
                target = tuple(max(-limit, min(limit, v)) for v in (self.rc if fresh else (0, 0, 0, 0)))
                # Ramp toward the target instead of jumping, so key presses and releases are smooth.
                self.rc_out = tuple(o + max(-step, min(step, t - o)) for o, t in zip(self.rc_out, target))
                try:
                    self.tello.send_rc_control(*self.rc_out)
                except Exception as exc:
                    self.note(f"Control error: {exc}")
            else:
                self.rc_out = (0, 0, 0, 0)
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
        if name == "land":  # always allowed, even mid-takeoff or if our flying flag is wrong
            if self.landing:
                return "already landing"
            self.landing = True
            threading.Thread(target=self._land, daemon=True).start()
            return "ok"
        if self.busy or self.landing:
            return f"busy ({'landing' if self.landing else self.busy})"
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
            self._takeoff()
        except Exception as exc:
            self.note(f"{name.capitalize()} failed: {exc} | {self.readings()}")
        finally:
            self.busy = ""

    def _land(self) -> None:
        """Fire "land" repeatedly instead of waiting on one reply.

        A waiting reply can be stolen by an in-flight takeoff, and the drone may ignore
        a single "land" while it is still climbing. Repeating is harmless once it is down.
        """
        self.note("Landing...")
        self.rc = (0, 0, 0, 0)
        start, sends, grounded = time.time(), 0, 0
        try:
            while time.time() - start < LAND_TIMEOUT_SECONDS:
                self.tello.send_command_without_return("land")
                sends += 1
                time.sleep(LAND_RESEND_SECONDS)
                grounded = grounded + 1 if self.value("get_height") <= 0 else 0
                if sends >= LAND_MIN_SENDS and grounded >= 2 and not self.busy:
                    break
            self.tello.is_flying = False
            self.note(f"Landed | {self.readings()}")
            threading.Timer(DRAIN_SETTLE_SECONDS, self._note_battery_drain, args=(time.time(),)).start()
        except Exception as exc:
            self.note(f"Land error: {exc}")
        finally:
            self.landing = False

    def readings(self) -> str:
        v = self.value
        return (f"battery {v('get_battery')}%, temp {v('get_lowest_temperature')}-{v('get_highest_temperature')}C, "
                f"pitch {v('get_pitch')} roll {v('get_roll')}, floor sensor {v('get_distance_tof')}cm")

    def preflight_problems(self) -> list[str]:
        t = self.tello
        problems = []
        if BATTERY_GUARD and t.get_battery() < LOW_BATTERY_PCT:
            problems.append(f"battery {t.get_battery()}% is too low, charge it")
        if t.get_highest_temperature() >= HOT_TEMP_C:
            problems.append(f"drone is {t.get_highest_temperature()}C, turn it off for 15 min to cool")
        if max(abs(t.get_pitch()), abs(t.get_roll())) > MAX_TILT_DEG:
            problems.append("drone is tilted: put it on a flat, level floor (not the stand or a box) before launch")
        if self.worn:
            rate = float(self.profile.get("drain_pct_per_min", NORMAL_DRAIN_PCT_PER_MIN)) / 60
            seconds = (t.get_battery() - self._land_floor_pct()) / rate
            if seconds < TAKEOFF_RESERVE_SECONDS:
                problems.append(f"battery {t.get_battery()}% leaves only ~{max(0, int(seconds))}s before this battery "
                                f"loses lift (around {self.profile['lift_loss_pct']}%). Charge it fully, or after "
                                f"swapping batteries delete {PROFILE_FILE}")
        return problems

    def _takeoff(self) -> None:
        problems = self.preflight_problems()
        if problems:
            self.note("Take off blocked: " + "; ".join(problems))
            return
        # One raw attempt (no silent retries) so we log the drone's exact reply.
        reply = self.tello.send_command_with_return("takeoff", timeout=TAKEOFF_TIMEOUT)
        if reply.strip().lower() == "ok":
            if self.landing:  # Land was pressed during the climb; don't flip back to flying
                self.note("Takeoff finished but a landing is in progress")
                return
            self.tello.is_flying = True
            self.flight_start = (time.time(), self.value("get_battery"))
            self.wobbled = False
            self.hover_steady_noted = False
            self.note("Takeoff done, hovering")
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
            "lift_left_s": self.lift_left_seconds(),
            "battery_worn": self.worn,
            "busy": "land" if self.landing else self.busy,
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


GAUGE_ACTIONS = ("baseline", "start", "stop", "corners")


def _corner_points(body: dict) -> tuple[list[list[float]] | None, str | None]:
    """Parse {"points": [[x, y] x4]} or {"clear": true}: (points or None to clear, error)."""
    if body.get("clear"):
        return None, None
    points = body.get("points")
    if not isinstance(points, list) or len(points) != 4:
        return None, "send 4 points: {\"points\": [[x, y], [x, y], [x, y], [x, y]]} or {\"clear\": true}"
    try:
        parsed = [[float(p[0]), float(p[1])] for p in points]
    except (TypeError, ValueError, IndexError):
        return None, "each point must be [x, y] numbers"
    if not all(0 <= v <= MAX_CORNER_PX for p in parsed for v in p):
        return None, "corner points must be pixel coordinates inside the frame"
    return parsed, None


def gauge_action(gauge: GaugeService | None, name: str, body: dict | None = None) -> tuple[dict, int]:
    """POST /gauge/<name>: (json body, http code)."""
    if gauge is None:
        return {"error": "gauge not running in this dashboard"}, 503
    if name not in GAUGE_ACTIONS:
        return {"error": "not found"}, 404
    if name == "corners":
        points, problem = _corner_points(body or {})
        if problem:
            return {"error": problem}, 400
        return {"result": gauge.set_corners(points)}, 200
    handlers = {"baseline": gauge.capture_baseline, "start": gauge.start, "stop": gauge.stop}
    return {"result": handlers[name]()}, 200


# Request guards. Any web page in the demo browser can send "simple" cross-origin POSTs to
# 127.0.0.1 without a preflight, and a DNS-rebinding page can even read responses. So: only
# accept our own Host, only local Origins, JSON bodies for POSTs (forces a CORS preflight, which
# this server never approves), and no cross-site GETs (no embedding the camera feed elsewhere).
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
LOCAL_ORIGIN_RE = re.compile(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?")
MAX_BODY_BYTES = 1024
MAX_VIDEO_STREAMS = 4
_video_slots = threading.BoundedSemaphore(MAX_VIDEO_STREAMS)


def request_problem(headers, is_post: bool) -> tuple[int, str] | None:
    """Why a request must be refused (status, message), or None if it is fine."""
    host = headers.get("Host", "")
    hostname = host.split("]", 1)[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
    if hostname not in ALLOWED_HOSTS:
        return 403, "bad host"
    origin = headers.get("Origin")
    if origin and not LOCAL_ORIGIN_RE.fullmatch(origin):
        return 403, "origin not allowed"
    if is_post and not headers.get("Content-Type", "").startswith("application/json"):
        return 415, "send JSON (Content-Type: application/json)"
    if not is_post and headers.get("Sec-Fetch-Site") == "cross-site":
        return 403, "cross-site request"
    return None


DEMO_FEATURES = 2500
DEMO_RATIO = 0.75  # Lowe ratio test
DEMO_MIN_INLIERS = 25
DEMO_RANSAC_PX = 4.0


class DemoTracker:
    """Keeps the hardcoded demo overlay on the tray while the drone moves.

    Anchor = a reference frame on which the overlay coordinates are defined. Each request matches ORB
    features between the reference and the latest frame and returns the homography that maps overlay
    points onto the current view. Too few inliers keeps the last good homography (reported as stale)."""

    def __init__(self, frame_source: Callable[[], np.ndarray | None]) -> None:
        self._frames = frame_source
        self._orb = cv2.ORB_create(DEMO_FEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._lock = threading.Lock()
        self._ref: tuple[Any, np.ndarray] | None = None
        self._h: np.ndarray | None = None
        self._ts = 0.0
        self._matched_frame = None
        self._inliers = 0
        self._last: tuple[Any, np.ndarray, np.ndarray] | None = None  # last tracked frame + its H

    def _features(self, frame_rgb: np.ndarray) -> tuple[Any, np.ndarray | None]:
        return self._orb.detectAndCompute(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY), None)

    def anchor(self) -> str:
        frame = self._frames()
        if frame is None:
            return "no video frame yet"
        kp, des = self._features(frame)
        if des is None or len(kp) < DEMO_MIN_INLIERS:
            return "not enough detail in view to track"
        with self._lock:
            self._ref, self._h, self._ts, self._inliers = (kp, des), np.eye(3), time.time(), len(kp)
            self._matched_frame = frame
            self._last = (kp, des, np.eye(3))
            record_event("demo_anchor_frame", frame=rgb_to_bgr(frame), features=len(kp))
        return "ok"

    def transform(self) -> dict[str, Any]:
        with self._lock:
            if self._ref is None:
                return {"anchored": False}
            frame = self._frames()
            if frame is not None and frame is not self._matched_frame:
                self._matched_frame = frame
                self._match(frame)
            result = {"anchored": True, "H": None if self._h is None else self._h.tolist(),
                    "inliers": self._inliers, "age_s": round(time.time() - self._ts, 2)}

            record_event("demo_transform", **result)
            return result

    def _match(self, frame: np.ndarray) -> None:
        kp, des = self._features(frame)
        ref_kp, ref_des = self._ref  # type: ignore[misc]
        if des is None or len(kp) < 2:
            return
        # Best: match the anchor directly (no drift). When the view has moved too far for that, chain
        # from the last tracked frame, which always overlaps the current one, and compose the shifts.
        direct = self._homography(ref_kp, ref_des, kp, des)
        if direct is not None:
            h, inliers = direct
        elif self._last is not None:
            step = self._homography(self._last[0], self._last[1], kp, des)
            if step is None:
                return
            h, inliers = step[0] @ self._last[2], step[1]
        else:
            return
        self._h, self._ts, self._inliers, self._last = h, time.time(), inliers, (kp, des, h)

    def _homography(self, kp_a: Any, des_a: np.ndarray, kp_b: Any, des_b: np.ndarray) -> tuple[np.ndarray, int] | None:
        good = [m for m, n in (p for p in self._matcher.knnMatch(des_a, des_b, k=2) if len(p) == 2)
                if m.distance < DEMO_RATIO * n.distance]
        if len(good) < DEMO_MIN_INLIERS:
            return None
        src = np.float32([kp_a[m.queryIdx].pt for m in good])
        dst = np.float32([kp_b[m.trainIdx].pt for m in good])
        h, mask = cv2.findHomography(src, dst, cv2.RANSAC, DEMO_RANSAC_PX)
        if h is None or mask is None or int(mask.sum()) < DEMO_MIN_INLIERS:
            return None
        return h, int(mask.sum())


def displayed_gauge(gauge, drone):
    status = gauge.status()
    renderer = getattr(drone, "live_overlay", None)
    if renderer is None:
        return status
    visible, value = renderer.gauge_value()
    if not visible:
        status.update({key: None for key in ESTIMATE_FIELDS})
        status["reason"] = "Waiting for visible tray or water"
    elif value is not None:
        status.update({key: None for key in ESTIMATE_FIELDS})
        status.update(ft=round(value, 2), ts=time.time(), age_s=0, reason=None, depth_source="manual")
    return status


def make_handler(drone: Drone, gauge: GaugeService | None = None, demo: DemoTracker | None = None):
    from live_overlay import LiveAnalysis, FrameOverlay
    if drone is not None and not hasattr(drone, "live_overlay"):
        drone.live_overlay = FrameOverlay()
    analysis = LiveAnalysis(lambda: drone.latest_frame(), record_event)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3.0)

        def log_message(self, *args) -> None:  # keep the console readable
            pass

        def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict, code: int = 200) -> None:
            self._send(json.dumps(data).encode(), "application/json", code)

        def _refused(self, is_post: bool) -> bool:
            problem = request_problem(self.headers, is_post)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).port != self.server.server_address[1]:
                problem = (403, "origin port not allowed")
            if problem:
                self._json({"error": problem[1]}, problem[0])
            return problem is not None

        def do_GET(self) -> None:
            if self._refused(is_post=False):
                return
            route = urlsplit(self.path).path
            if route == "/":
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif route == "/status":
                try:
                    self._json(drone.status())
                except Exception as exc:
                    self._json({"error": str(exc)}, 503)
            elif route == "/video":
                self._stream_video()
            elif route.startswith("/gauge/"):
                self._gauge_get(route)
            elif route == "/analysis/render-status":
                renderer = drone.live_overlay
                with renderer.lock:
                    self._json({"processing_ms": renderer.ms, "regions": list(renderer.regions)})
            elif route == "/analysis/status":
                result = analysis.status()
                result["gauge"] = displayed_gauge(gauge, drone) if gauge else {}
                self._json(result)
            elif route == "/demo/transform":
                self._json(demo.transform() if demo else {"anchored": False})
            else:
                self._json({"error": "not found"}, 404)

        def _gauge_get(self, route: str) -> None:
            if gauge is None:
                return self._json({"error": "gauge not running in this dashboard"}, 503)
            if route == "/gauge/status":
                try:
                    return self._json(displayed_gauge(gauge, drone))
                except Exception as exc:  # noqa: BLE001
                    return self._json({"error": str(exc)}, 503)
            if route == "/gauge/overlay.jpg":
                jpeg = gauge.overlay_jpeg
                return self._send(jpeg, "image/jpeg") if jpeg else self._json({"error": "no overlay for the latest reading"}, 404)
            return self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            if self._refused(is_post=True):
                return None
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= MAX_BODY_BYTES:
                    return self._json({"error": "request body too large"}, 413)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return self._json({"error": "body must be a JSON object"}, 400)
            route = urlsplit(self.path).path  # same routing as GET: a ?query never changes the target
            if route == "/analysis/config":
                allowed = {"enabled", "water", "car", "tray", "labels", "demo_depth", "demo_stddev", "car_points", "tray_points"}
                if set(body) - allowed:
                    return self._json({"error": "unknown setting"}, 400)
                for key, value in body.items():
                    if key.endswith("_points"):
                        count = 4
                        if (not isinstance(value, list) or len(value) != count or
                            any(not isinstance(p, list) or len(p) != 2 or
                                any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                                    not math.isfinite(v) or not 0 <= v <= 4096 for v in p) for p in value)):
                            return self._json({"error": "send four finite image points"}, 400)
                    elif key in ("demo_depth", "demo_stddev"):
                        if (value is None and key == "demo_stddev") or value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                                  or not math.isfinite(value) or not 0 <= value <= 100):
                            return self._json({"error": "depth must be between 0 and 100"}, 400)
                    elif not isinstance(value, bool):
                        return self._json({"error": "visibility settings must be boolean"}, 400)
                drone.live_overlay.configure(body)
                record_event("overlay_config", settings=body)
                return self._json({"result": "ok"})
            if route == "/rc":
                values = [body.get(key, 0) for key in ("lr", "fb", "ud", "yaw")]
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                       not math.isfinite(value) for value in values):
                    return self._json({"error": "controls must be finite numbers"}, 400)
                drone.set_rc(body)
                return self._json({"result": "ok"})
            if route == "/shutdown":  # a newer dashboard is taking over (localhost only)
                self._json({"result": "ok"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            if route == "/demo/anchor":
                result = demo.anchor() if demo else "demo tracking not running"
                record_event("demo_anchor", result=result)
                return self._json({"result": result})
            if route.startswith("/gauge/"):
                data, code = gauge_action(gauge, route.removeprefix("/gauge/"), body)
                record_event("gauge_action", route=route, request=body, response=data, status=code)
                return self._json(data, code)
            name = route.removeprefix("/action/")
            if route.startswith("/action/") and name in ACTIONS:
                result = drone.action(name)
                record_event("flight_action", action=name, result=result)
                return self._json({"result": result})
            self._json({"error": "not found"}, 404)

        def _stream_video(self) -> None:
            if not _video_slots.acquire(blocking=False):
                return self._json({"error": "too many video streams open"}, 503)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    jpeg = drone.jpeg
                    if jpeg:
                        head = f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
                        self.wfile.write(head.encode() + jpeg + b"\r\n")
                    time.sleep(FRAME_SECONDS)
            except OSError:
                return None  # browser closed the stream
            finally:
                _video_slots.release()

    return Handler


def bind_server() -> DashboardServer | None:
    """Take the port. If an older dashboard holds it, ask that one to land and exit first."""
    try:
        return DashboardServer((HOST, PORT), make_handler(None))
    except OSError:
        pass
    write_log("Another dashboard is running; asking it to shut down...")
    try:
        req = urllib.request.Request(f"http://{HOST}:{PORT}/shutdown", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
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
    global RUN_DIR
    folder = LOG_FILE.parent / "runs" / (time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns()}")
    try:
        folder.mkdir(parents=True)
        RUN_DIR = folder
    except OSError as exc:
        print(f"Could not create run log: {exc}", file=sys.stderr)
    write_log(f"Dashboard starting. Run log: {RUN_DIR}")
    server = bind_server()
    if server is None:
        write_log(f"An older dashboard is STILL RUNNING on port {PORT} and would not close.")
        print("Close the other black 'Tello dashboard' window (or end python.exe in Task Manager), "
              "then try again.")
        return
    drone = Drone(Tello())
    write_log("Connecting to the drone...")
    drone.start()
    from live_overlay import FrameOverlay
    drone.live_overlay = FrameOverlay()
    gauge = GaugeService(frame_source=drone.latest_frame, note=drone.note,
                         geometry_sink=drone.live_overlay.seed_geometry)
    done = threading.Event()
    threading.Thread(target=record_telemetry, args=(drone, done), daemon=True).start()
    gauge.preload()
    def begin_gauge():
        gauge._ensure_reader()
        gauge.start()
    threading.Thread(target=begin_gauge, daemon=True).start()
    server.RequestHandlerClass = make_handler(drone, gauge, DemoTracker(drone.latest_frame))
    url = f"http://{HOST}:{PORT}"
    print(f"Dashboard running at {url}  (press Ctrl+C here to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        gauge.stop()
        done.set()
        drone.shutdown()
        server.server_close()
        record_event("dashboard_stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        write_log("CRASH: " + traceback.format_exc())
        raise
