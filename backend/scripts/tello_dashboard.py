"""Unified Tello dashboard: live video, telemetry, and keyboard/mouse flight control in a browser.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello dashboard" on the Desktop.
It opens http://127.0.0.1:8765 in your browser. Works offline. Press Ctrl+C in the console to stop
(the drone lands first if it is flying).
"""

import json
import os
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

BACKEND_DIR = Path(__file__).resolve().parents[1]  # holds the `gauge` package
GAUGE_HZ = 2
GAUGE_DYE_DEFAULT = "blue"
GAUGE_LOADING = "loading the gauge model"
GAUGE_ERROR_WAIT_SECONDS = 1.0  # back off after a reader error so a bad frame can't spin the CPU
ESTIMATE_FIELDS = (
    "level_mm", "level_mm_range", "ft", "ft_range", "confidence", "crossing_flooded", "car_level",
    "houses_flooded", "houses_total", "visible_cells", "wet_cells", "tags_seen", "reproj_err_px",
    "has_baseline", "simulated", "reason", "ts",
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
    return GaugeReader(load_tray(), load_intrinsics(), dye=dye)


def encode_jpeg(frame_bgr: np.ndarray) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def rgb_to_bgr(frame_rgb: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(frame_rgb[:, :, ::-1])


def jsonable(value: Any) -> Any:
    """numpy scalars and tuples from the estimate -> plain JSON types."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


class GaugeService:
    """Reads the gauge tray water level from the latest frame at about GAUGE_HZ while enabled.

    Runs on its own thread and touches the drone only through `frame_source`, so a slow or
    failing reader can never stall telemetry or flight control. Reader errors are logged once
    per distinct message and reported in status()["error"].
    """

    def __init__(self, frame_source: Callable[[], np.ndarray | None], note: Callable[[str], None],
                 reader_factory: Callable[[], GaugeReaderLike] = default_gauge_reader,
                 encoder: Callable[[np.ndarray], bytes | None] = encode_jpeg,
                 interval: float = 1 / GAUGE_HZ) -> None:
        self._frame_source = frame_source  # RGB frames, as djitellopy delivers them
        self._note = note
        self._reader_factory = reader_factory
        self._encoder = encoder
        self._interval = interval
        self._reader: GaugeReaderLike | None = None
        self._unavailable = ""  # why the gauge package could not load; set once
        self._load_lock = threading.Lock()
        self._reader_lock = threading.Lock()  # baseline and update never run at the same time
        self._thread: threading.Thread | None = None
        self.enabled = False
        self.has_baseline = False
        self.estimate: dict[str, Any] = {}
        self.overlay_jpeg: bytes | None = None
        self.error: str | None = None
        self._preloading = False

    def _ensure_reader(self, retry: bool = False) -> GaugeReaderLike | None:
        """Load once. `retry` (a button press) tries again after a failure, e.g. once the package is fixed."""
        with self._load_lock:
            if retry and self._reader is None:
                self._unavailable = ""
            if self._reader is None and not self._unavailable:
                try:
                    self._reader = self._reader_factory()
                    self._note("Water gauge ready")
                except Exception as exc:  # noqa: BLE001 - ImportError, missing tray data, bad camera json
                    self._unavailable = f"{type(exc).__name__}: {exc}"
                    self.error = self._unavailable
                    self._note(f"Water gauge unavailable ({self._unavailable})")
            return self._reader

    def _frame_bgr(self) -> np.ndarray | None:
        frame = self._frame_source()
        return None if frame is None else rgb_to_bgr(frame)

    def capture_baseline(self) -> str:
        reader = self._ensure_reader(retry=True)
        if reader is None:
            return f"gauge unavailable: {self._unavailable}"
        frame = self._frame_bgr()
        if frame is None:
            return "no video frame yet"
        try:
            with self._reader_lock:
                ok, reason = reader.set_baseline(frame)
        except Exception as exc:  # noqa: BLE001 - contain reader faults
            return self._record_error("Baseline", exc)
        self.has_baseline = self.has_baseline or bool(ok)
        self._note("Water gauge: dry baseline captured" if ok else f"Water gauge baseline refused: {reason}")
        return "ok" if ok else str(reason)

    def start(self) -> str:
        if self._ensure_reader(retry=True) is None:
            return f"gauge unavailable: {self._unavailable}"
        self.enabled = True
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            self._note("Water gauge reading started")
        return "ok"

    def stop(self) -> str:
        if self.enabled:
            self._note("Water gauge reading stopped")
        self.enabled = False
        return "ok"

    def _loop(self) -> None:
        last_frame = None
        while self.enabled:
            frame = self._frame_source()
            if frame is None or frame is last_frame:
                time.sleep(self._interval)
                continue
            last_frame = frame
            self.read_once(rgb_to_bgr(frame))
            time.sleep(self._interval if self.error is None else GAUGE_ERROR_WAIT_SECONDS)

    def read_once(self, frame_bgr: np.ndarray) -> None:
        """One reading: smoothed estimate plus the annotated overlay. Never raises."""
        reader = self._reader
        if reader is None:
            return
        try:
            with self._reader_lock:
                estimate = reader.update(frame_bgr)
                overlay = reader.overlay(frame_bgr, estimate)
            self.estimate = jsonable(estimate.to_dict())
            self.overlay_jpeg = self._encoder(overlay) or self.overlay_jpeg
            self.error = None
        except Exception as exc:  # noqa: BLE001 - contain reader faults
            self._record_error("Reader", exc)

    def _record_error(self, what: str, exc: Exception) -> str:
        message = f"{what} error: {type(exc).__name__}: {exc}"
        if message != self.error:  # log once per distinct error, not twice a second
            self._note(f"Water gauge {message}")
        self.error = message
        return message

    @property
    def running(self) -> bool:
        return self.enabled and self._thread is not None and self._thread.is_alive()

    def preload(self) -> None:
        """Load the gauge model in the background so the first status poll answers at once."""
        if self._preloading:
            return
        self._preloading = True
        threading.Thread(target=self._ensure_reader, daemon=True).start()

    def status(self) -> dict[str, Any]:
        """Never blocks on loading: while the model loads, report unavailable with that reason."""
        loading = self._reader is None and not self._unavailable
        if loading:
            self.preload()
        estimate = {k: self.estimate.get(k) for k in ESTIMATE_FIELDS}
        estimate["has_baseline"] = bool(estimate["has_baseline"] or self.has_baseline)
        return {
            "gauge": "online" if self._reader is not None else "unavailable",
            "enabled": self.enabled,
            "running": self.running,
            "error": self.error or (GAUGE_LOADING if loading else None),
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
        """One CSV row per second while flying, so a bad flight can be read back afterwards."""
        if not self.tello.is_flying:
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
        return "lift_loss_pct" in self.profile

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
                    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), params)
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
        if t.get_battery() < LOW_BATTERY_PCT:
            problems.append(f"battery {t.get_battery()}% is too low, charge it")
        if t.get_highest_temperature() >= HOT_TEMP_C:
            problems.append(f"drone is {t.get_highest_temperature()}C, turn it off for 15 min to cool")
        if max(abs(t.get_pitch()), abs(t.get_roll())) > MAX_TILT_DEG:
            problems.append("drone is tilted, put it on a flat surface")
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


GAUGE_ACTIONS = ("baseline", "start", "stop")


def gauge_action(gauge: GaugeService | None, name: str) -> tuple[dict, int]:
    """POST /gauge/<name>: (json body, http code)."""
    if gauge is None:
        return {"error": "gauge not running in this dashboard"}, 503
    if name not in GAUGE_ACTIONS:
        return {"error": "not found"}, 404
    handlers = {"baseline": gauge.capture_baseline, "start": gauge.start, "stop": gauge.stop}
    return {"result": handlers[name]()}, 200


def make_handler(drone: Drone, gauge: GaugeService | None = None):
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
            elif self.path.startswith("/gauge/"):
                self._gauge_get(urlsplit(self.path).path)
            else:
                self._json({"error": "not found"}, 404)

        def _gauge_get(self, route: str) -> None:
            if gauge is None:
                return self._json({"error": "gauge not running in this dashboard"}, 503)
            if route == "/gauge/status":
                try:
                    return self._json(gauge.status())
                except Exception as exc:  # noqa: BLE001
                    return self._json({"error": str(exc)}, 503)
            if route == "/gauge/overlay.jpg":
                jpeg = gauge.overlay_jpeg
                return self._send(jpeg, "image/jpeg") if jpeg else self._json({"error": "no reading yet"}, 404)
            return self._json({"error": "not found"}, 404)

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
            if self.path.startswith("/gauge/"):
                data, code = gauge_action(gauge, self.path.removeprefix("/gauge/"))
                return self._json(data, code)
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
    gauge = GaugeService(frame_source=drone.latest_frame, note=drone.note)
    gauge.preload()
    server.RequestHandlerClass = make_handler(drone, gauge)
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
