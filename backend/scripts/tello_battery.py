"""Live battery monitor for a DJI Tello. Prints battery and temperature every few seconds.

Connect to the TELLO-XXXXXX Wi-Fi, then double-click "Tello battery" on the Desktop.
Close the window (or press Ctrl+C) to stop. Uses command/response only, no state port needed.
"""

import time

from djitellopy import Tello

INTERVAL_SECONDS = 5
LOW_BATTERY_PCT = 20
CRITICAL_BATTERY_PCT = 10


def label(pct: int) -> str:
    if pct <= CRITICAL_BATTERY_PCT:
        return "CRITICAL - land and charge now"
    if pct <= LOW_BATTERY_PCT:
        return "LOW - don't take off"
    return "OK to fly"


def bar(pct: int, width: int = 20) -> str:
    filled = round(width * pct / 100)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> None:
    tello = Tello()
    tello.connect(wait_for_state=False)
    print("Connected. Updating every", INTERVAL_SECONDS, "seconds. Close the window to stop.\n")
    try:
        while True:
            pct = tello.query_battery()
            temp = tello.send_read_command("temp?")
            stamp = time.strftime("%H:%M:%S")
            print(f"{stamp}  {bar(pct)} {pct:3d}%  temp {temp}  {label(pct)}")
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        tello.end()


if __name__ == "__main__":
    main()
