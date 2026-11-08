"""Health check for a DJI Tello: does it answer, and what does it report about itself.

Connect the laptop to the Tello's Wi-Fi (TELLO-XXXXXX) first, then double-click tello_check.bat.
Uses only command/response queries, so it works even if the firewall blocks the state port.
"""

from djitellopy import Tello

HOT_TEMP_C = 80
LOW_BATTERY_PCT = 15

# Raw "?" commands: the library's parsed versions break on this firmware (temp is "61~63C").
QUERIES = {
    "Battery (%)": "battery?",
    "Temperature (C)": "temp?",
    "Attitude (pitch/roll/yaw)": "attitude?",
    "Wi-Fi signal/noise": "wifi?",
}


def ask(tello: Tello, command: str) -> str:
    try:
        return str(tello.send_read_command(command))
    except Exception as exc:  # report every failure, keep checking the rest
        return f"no answer ({exc.__class__.__name__})"


def main() -> None:
    tello = Tello()
    print("Talking to the drone...")
    try:
        tello.connect(wait_for_state=False)
    except Exception as exc:
        print("\nFAILED: the drone did not answer.")
        print("  - Is the laptop on the TELLO-XXXXXX Wi-Fi?")
        print("  - Power-cycle the drone and try again.")
        print("  - If it still fails while the light is solid red, the drone has a fault.")
        print(f"  (details: {exc})")
        return

    print("OK: the drone answered.\n")
    results = {label: ask(tello, method) for label, method in QUERIES.items()}
    for label, value in results.items():
        print(f"  {label:28} {value}")

    print()
    battery = results["Battery (%)"]
    if battery.isdigit() and int(battery) < LOW_BATTERY_PCT:
        print("WARNING: battery is low. Charge it fully.")
    temp = "".join(ch for ch in results["Temperature (C)"] if ch.isdigit() or ch == "~")
    highs = [int(t) for t in temp.split("~") if t.isdigit()]
    if highs and max(highs) >= HOT_TEMP_C:
        print("WARNING: the drone is hot. Turn it off and let it cool 15 minutes.")
    print("Next: double-click tello_stream.bat to test the video.")
    tello.end()


if __name__ == "__main__":
    main()
