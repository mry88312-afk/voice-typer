@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo Adding Voice Typer to Windows Startup...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$startup = [Environment]::GetFolderPath('Startup');" ^
  "$target = (Resolve-Path '%~dp0start.vbs').Path;" ^
  "$workdir = (Resolve-Path '%~dp0').Path;" ^
  "$icon = (Resolve-Path '%~dp0venv\Scripts\pythonw.exe').Path;" ^
  "$lnk = $ws.CreateShortcut((Join-Path $startup 'Voice Typer.lnk'));" ^
  "$lnk.TargetPath = $target; $lnk.WorkingDirectory = $workdir; $lnk.IconLocation = $icon; $lnk.Save();" ^
  "Write-Host ('Added: ' + (Join-Path $startup 'Voice Typer.lnk')) -ForegroundColor Green"

echo.
echo Voice Typer will now auto-launch when Windows starts.
echo To disable: delete the shortcut in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
pause
