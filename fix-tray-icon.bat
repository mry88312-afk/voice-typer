@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo  Fix Tray Icon Visibility (Windows 11)
echo ============================================
echo.
echo This will force Voice Typer icon to show on the taskbar
echo instead of being hidden in the overflow area.
echo.
echo It will:
echo   1. Modify registry (HKCU only, no admin needed)
echo   2. Restart Windows Explorer
echo   3. Relaunch Voice Typer
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Write-Host 'Stopping pythonw...' -ForegroundColor Yellow;" ^
  "Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force;" ^
  "Start-Sleep -Milliseconds 500;" ^
  "Write-Host 'Setting registry: show all tray icons...' -ForegroundColor Yellow;" ^
  "$key = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\TrayNotify';" ^
  "if (!(Test-Path $key)) { New-Item -Path $key -Force | Out-Null };" ^
  "Set-ItemProperty -Path $key -Name 'SystemTrayChevronVisibility' -Value 0 -Type DWord;" ^
  "Write-Host 'Restarting Explorer (taskbar will flicker)...' -ForegroundColor Yellow;" ^
  "Stop-Process -Name explorer -Force; Start-Sleep -Seconds 2;" ^
  "if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) { Start-Process explorer };" ^
  "Start-Sleep -Seconds 2;" ^
  "Write-Host 'Relaunching Voice Typer...' -ForegroundColor Green;" ^
  "Start-Process -FilePath '%~dp0venv\Scripts\pythonw.exe' -ArgumentList 'main.py' -WorkingDirectory '%~dp0';" ^
  "Write-Host '' ;" ^
  "Write-Host 'Done! Look for the green microphone icon in the tray.' -ForegroundColor Green"

echo.
pause
