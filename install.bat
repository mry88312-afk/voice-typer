@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo  Voice Typer - Installer
echo ============================================
echo.

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.9+ first:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Python version:
python --version
echo.

if not exist venv (
    echo [2/4] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
) else (
    echo [2/4] venv already exists, skip
)
echo.

echo [3/4] Installing packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package install failed
    pause
    exit /b 1
)
echo.

echo [4/4] Setting up .env...
if not exist .env (
    copy .env.example .env >nul
    echo .env created, please edit and add your OPENAI_API_KEY
) else (
    echo .env already exists, skip
)

echo.
echo ============================================
echo  Install complete!
echo.
echo  Next steps:
echo  1. Open .env in Notepad, set OPENAI_API_KEY
echo  2. Double-click run.bat to start
echo ============================================
pause
