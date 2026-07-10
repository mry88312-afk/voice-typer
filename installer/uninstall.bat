@echo off
chcp 65001 >nul 2>&1
echo 解除安裝 Voice Typer...
taskkill /IM VoiceTyper.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VoiceTyper.lnk" >nul 2>&1
del "%USERPROFILE%\Desktop\Voice Typer.lnk" >nul 2>&1
del "%USERPROFILE%\OneDrive\Desktop\Voice Typer.lnk" >nul 2>&1
del "%USERPROFILE%\OneDrive\桌面\Voice Typer.lnk" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\Programs\VoiceTyper" >nul 2>&1
echo.
echo 程式已移除。
echo 你的個人設定與 API Key 仍保留在：%APPDATA%\VoiceTyper
echo （若要一併刪除，請手動刪除該資料夾。）
pause
