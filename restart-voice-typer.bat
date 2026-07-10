@echo off
chcp 65001 >nul 2>&1
echo 正在重啟 Voice Typer...
taskkill /IM VoiceTyper.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "C:\Users\mry88\voice-typer\dist\VoiceTyper\VoiceTyper.exe"
