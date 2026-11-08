"""Show live video from a DJI Tello in a window.

Connect the laptop to the Tello's Wi-Fi (TELLO-XXXXXX) first, then double-click
tello_stream.bat, or run:
    %USERPROFILE%\tello-env\Scripts\python.exe scripts\tello_stream.py
Press q in the video window to quit. Full offline steps: TELLO_STEPS.txt.
"""

import cv2
from djitellopy import Tello


def main() -> None:
    tello = Tello()
    tello.connect()
    print("Battery:", tello.get_battery(), "%")
    tello.streamon()

    frame_read = tello.get_frame_read()
    try:
        while True:
            frame = frame_read.frame
            if frame is not None:
                # If colors look swapped, drop the cvtColor call.
                cv2.imshow("Tello", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        tello.streamoff()
        tello.end()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
