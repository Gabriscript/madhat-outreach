@echo off
rem Starts the app without a console window, from this folder so settings paths resolve
cd /d "%~dp0"
start "" venv\Scripts\pythonw.exe app\run.py
