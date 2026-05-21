@echo off
REM Run as Administrator (sometimes needed for keyboard global hotkey)
chcp 65001 >nul 2>&1

net session >nul 2>&1
if errorlevel 1 (
    echo Need administrator privileges, relaunching...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
call venv\Scripts\activate.bat
python main.py
pause
