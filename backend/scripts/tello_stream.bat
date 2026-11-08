@echo off
rem Double-click to show live Tello video. Connect to the TELLO-XXXXXX Wi-Fi first.
"%USERPROFILE%\tello-env\Scripts\python.exe" "%~dp0tello_stream.py"
pause
