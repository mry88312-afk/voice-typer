@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] venv not found. Run install.bat first.
    pause
    exit /b 1
)

if not exist .env (
    echo [ERROR] .env not found. Run install.bat and set API key first.
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
call venv\Scripts\activate.bat
python main.py
pause
