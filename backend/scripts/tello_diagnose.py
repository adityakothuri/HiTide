"""Diagnose why a Tello refuses to take off. Writes ~/tello-test/diagnose.txt.

Connect to the TELLO-XXXXXX Wi-Fi, put the drone on the floor, double-click "Tello diagnose".
It checks the sensors, light, heat and battery, then (only after you press Enter) sends ONE
takeoff and records the drone's exact reply. If it does take off, it lands right away.
"""

import os
import statistics
import sys
import threading
import time
from pathlib import Path

from djitellopy import Tello

sys.path.insert(0, str(Path(__file__).parent))
from tello_dashboard import flush_replies  # noqa: E402

OUT = Path.home() / "tello-test"
REPORT = OUT / "diagnose.txt"
SAMPLES = 10
GRAVITY_MG = 1000  # agz reads about -1000 when sitting still and flat
IMU_TOLERANCE_MG = 250
MAX_TILT_DEG = 10
HOT_TEMP_C = 80
LOW_BATTERY_PCT = 20
DARK_BRIGHTNESS = 45  # mean pixel 0-255
VIDEO_TIMEOUT = 25
TAKEOFF_TIMEOUT = 20
HOVER_SECONDS = 3

lines: list[str] = []
findings: list[str] = []


def log(text: str) -> None:
    lines.append(f"{time.strftime('%H:%M:%S')}  {text}")
    print(text)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find(text: str) -> None:
    findings.append(text)
    log(f"  >> {text}")


def sample_state(tello: Tello) -> dict:
    rows = []
    for _ in range(SAMPLES):
        rows.append(dict(tello.get_current_state()))
        time.sleep(0.1)
    keys = rows[-1].keys()
    return {k: statistics.median(float(r[k]) for r in rows if k in r) for k in keys
            if all(isinstance(r.get(k), (int, float)) for r in rows)}


def check_state(s: dict) -> None:
    log("Sensor readings (median of 10): " + ", ".join(f"{k}={v:g}" for k, v in sorted(s.items())))
    bat, temph = s.get("bat", 0), s.get("temph", 0)
    tilt = max(abs(s.get("pitch", 0)), abs(s.get("roll", 0)))
    agx, agy, agz = s.get("agx", 0), s.get("agy", 0), s.get("agz", 0)
    if bat < LOW_BATTERY_PCT:
        find(f"BATTERY LOW ({bat:g}%). Charge it.")
    if temph >= HOT_TEMP_C:
        find(f"TOO HOT ({temph:g}C). Turn it off for 15 minutes.")
    if tilt > MAX_TILT_DEG:
        find(f"TILTED ({tilt:g} deg). Put it on a flat surface.")
    if abs(abs(agz) - GRAVITY_MG) > IMU_TOLERANCE_MG or max(abs(agx), abs(agy)) > IMU_TOLERANCE_MG:
        find(f"MOTION SENSOR (IMU) LOOKS WRONG (agx={agx:g} agy={agy:g} agz={agz:g}, expected ~0/0/-1000). "
             "Do IMU calibration in the Tello phone app.")
    else:
        log(f"  IMU looks sane (agz={agz:g}, expected about -1000).")


def measure_light(tello: Tello) -> float | None:
    box: dict = {}

    def grab() -> None:
        tello.streamon()
        reader = tello.get_frame_read()
        deadline = time.time() + 5
        while time.time() < deadline:
            frame = reader.frame
            if frame is not None and frame.any():
                box["frame"] = frame
            time.sleep(0.1)

    worker = threading.Thread(target=grab, daemon=True)
    worker.start()
    worker.join(VIDEO_TIMEOUT)
    frame = box.get("frame")
    if frame is None:
        log("  Could not read video to measure light (skipped).")
        return None
    brightness = float(frame.mean())
    import cv2

    cv2.imwrite(str(OUT / "diagnose_view.jpg"), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    log(f"Camera brightness: {brightness:.0f}/255 (snapshot saved as diagnose_view.jpg)")
    if brightness < DARK_BRIGHTNESS:
        find(f"ROOM TOO DARK (brightness {brightness:.0f}). The downward camera can't see the floor. "
             "Turn on the lights.")
    return brightness


def try_takeoff(tello: Tello) -> str:
    input("\nPut the drone on the floor with 2 m clear around it, then press Enter to try ONE takeoff "
          "(or close this window to skip)... ")
    flush_replies(tello)
    start = time.time()
    reply = tello.send_command_with_return("takeoff", timeout=TAKEOFF_TIMEOUT).strip()
    log(f"Takeoff reply: '{reply}' after {time.time() - start:.1f}s")
    if reply.lower() == "ok":
        log("It FLEW. Hovering briefly, then landing.")
        time.sleep(HOVER_SECONDS)
        flush_replies(tello)
        log(f"Land reply: '{tello.send_command_with_return('land', timeout=TAKEOFF_TIMEOUT).strip()}'")
    return reply


def verdict(reply: str) -> None:
    log("\n===== VERDICT =====")
    if reply.lower() == "ok":
        log("The drone takes off fine here. If the dashboard failed before, the room/heat/position "
            "was the difference. Try the dashboard again in these same conditions.")
        return
    detail = reply.lower()
    if "imu" in detail:
        findings.insert(0, "Drone says its IMU is invalid: do IMU calibration in the Tello phone app.")
    elif "motor" in detail:
        findings.insert(0, "Drone reports a motor problem: check every propeller spins freely and is on the right motor.")
    elif "low" in detail or "battery" in detail:
        findings.insert(0, "Drone says the battery is too low: charge it.")
    if findings:
        for i, text in enumerate(findings, 1):
            log(f"{i}. {text}")
    else:
        log("Sensors, light, heat and battery all look fine, but the drone still refuses. Most likely "
            "it needs IMU calibration and/or a firmware update: Tello phone app > Settings > More > "
            "IMU Calibration, and install any update it offers. Then run this again.")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    log("Tello diagnosis")
    tello = Tello()
    try:
        tello.connect()
        flush_replies(tello)
    except Exception as exc:
        log(f"Could not connect: {exc}. Is the laptop on the TELLO Wi-Fi and the drone on?")
        return
    log(f"Connected. Raw replies: battery={tello.send_read_command('battery?')}, "
        f"temp={tello.send_read_command('temp?')}")
    check_state(sample_state(tello))
    measure_light(tello)
    reply = try_takeoff(tello)
    verdict(reply)
    log(f"\nDone. Full report: {REPORT}")


if __name__ == "__main__":
    main()
    input("\nPress Enter to close.")
    os._exit(0)  # don't wait on the video thread
