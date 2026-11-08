@echo off
rem Double-click to check the Tello responds. Connect to the TELLO-XXXXXX Wi-Fi first.
"%USERPROFILE%\tello-env\Scripts\python.exe" "%~dp0tello_check.py"
pause
