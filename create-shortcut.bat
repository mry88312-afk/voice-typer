@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo Creating Desktop and Start Menu shortcuts for Voice Typer...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$startMenu = [Environment]::GetFolderPath('Programs');" ^
  "$target = (Resolve-Path '%~dp0start.vbs').Path;" ^
  "$workdir = (Resolve-Path '%~dp0').Path;" ^
  "$icon = (Resolve-Path '%~dp0venv\Scripts\pythonw.exe').Path;" ^
  "$sc1 = $ws.CreateShortcut((Join-Path $desktop 'Voice Typer.lnk'));" ^
  "$sc1.TargetPath = $target; $sc1.WorkingDirectory = $workdir; $sc1.IconLocation = $icon; $sc1.Description = 'Voice Typer - 語音輸入工具'; $sc1.Save();" ^
  "$sc2 = $ws.CreateShortcut((Join-Path $startMenu 'Voice Typer.lnk'));" ^
  "$sc2.TargetPath = $target; $sc2.WorkingDirectory = $workdir; $sc2.IconLocation = $icon; $sc2.Description = 'Voice Typer - 語音輸入工具'; $sc2.Save();" ^
  "Write-Host 'Done!' -ForegroundColor Green;" ^
  "Write-Host ('Desktop:    ' + (Join-Path $desktop 'Voice Typer.lnk'));" ^
  "Write-Host ('Start Menu: ' + (Join-Path $startMenu 'Voice Typer.lnk'))"

echo.
echo ============================================
echo Shortcuts created!
echo You can now launch Voice Typer from:
echo   - Desktop (double-click "Voice Typer")
echo   - Start Menu (search "Voice Typer")
echo ============================================
pause
