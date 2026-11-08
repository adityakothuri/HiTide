"""Fly a DJI Tello from the laptop keyboard with live video (Windows only).

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello fly" on the Desktop.
Keys only work while the "Tello" video window is the active window.

    T          take off             L      land
    W / S      forward / back       A / D  left / right
    Up / Down  climb / descend      Left / Right  turn
    Esc        land and quit        Backspace  EMERGENCY motor stop (drone drops)
"""

import ctypes
import time

import cv2
from djitellopy import Tello

WINDOW = "Tello"
SPEED = 50  # rc speed, -100..100
LOOP_SECONDS = 0.03
LOW_BATTERY_PCT = 15

VK = {
    "W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "T": 0x54, "L": 0x4C,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "ESC": 0x1B, "BACKSPACE": 0x08,
}

user32 = ctypes.windll.user32


def window_active() -> bool:
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(hwnd, buf, 64)
    return buf.value == WINDOW


def down(name: str) -> bool:
    return bool(user32.GetAsyncKeyState(VK[name]) & 0x8000)


def axis(positive: str, negative: str) -> int:
    return SPEED * (int(down(positive)) - int(down(negative)))


def draw_hud(frame, tello: Tello, flying: bool):
    img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    battery = tello.get_battery()
    color = (0, 0, 255) if battery < LOW_BATTERY_PCT else (0, 255, 0)
    status = f"Battery {battery}%  Height {tello.get_height()}cm  {'FLYING' if flying else 'LANDED'}"
    cv2.putText(img, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    cv2.putText(img, "T takeoff  L land  WASD move  arrows up/down/turn  Esc quit",
                (10, img.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return img


def fly_loop(tello: Tello) -> None:
    """Run until Esc or emergency stop."""
    frame_read = tello.get_frame_read()
    while True:
        frame = frame_read.frame
        if frame is not None:
            cv2.imshow(WINDOW, draw_hud(frame, tello, tello.is_flying))
        cv2.waitKey(1)
        time.sleep(LOOP_SECONDS)
        if not window_active():
            tello.send_rc_control(0, 0, 0, 0)
            continue
        if down("BACKSPACE"):
            tello.emergency()
            tello.is_flying = False
            return
        if down("ESC"):
            return
        if down("T") and not tello.is_flying:
            tello.takeoff()
        elif down("L") and tello.is_flying:
            tello.land()
        elif tello.is_flying:
            tello.send_rc_control(axis("D", "A"), axis("W", "S"),
                                  axis("UP", "DOWN"), axis("RIGHT", "LEFT"))


def main() -> None:
    tello = Tello()
    tello.connect()
    print("Battery:", tello.get_battery(), "%")
    if tello.get_battery() < LOW_BATTERY_PCT:
        print("Battery too low to fly safely. Charge it first.")
    tello.streamon()
    try:
        fly_loop(tello)
    finally:
        if tello.is_flying:
            tello.send_rc_control(0, 0, 0, 0)
            tello.land()
        tello.streamoff()
        tello.end()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
