@echo off
chcp 65001 >nul 2>&1
set DEST=%LOCALAPPDATA%\Programs\VoiceTyper
echo 安裝 Voice Typer 到 %DEST% ...
robocopy "%~dp0VoiceTyper" "%DEST%" /MIR /NFL /NDL /NJH /NJS
if %ERRORLEVEL% GEQ 8 (echo 複製失敗 & pause & exit /b 1)
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $lnk=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'VoiceTyper.lnk')); $lnk.TargetPath=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper\VoiceTyper.exe'); $lnk.Arguments='--autostart'; $lnk.WorkingDirectory=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper'); $lnk.Save()"
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $lnk=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Voice Typer.lnk')); $lnk.TargetPath=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper\VoiceTyper.exe'); $lnk.WorkingDirectory=(Join-Path $env:LOCALAPPDATA 'Programs\VoiceTyper'); $lnk.Save()"
echo 安裝完成，正在啟動（首次會出現設定精靈，請填入 API Key）...
start "" "%DEST%\VoiceTyper.exe"
pause
