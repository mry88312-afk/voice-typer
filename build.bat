@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo [1/4] 關閉執行中的 VoiceTyper...
taskkill /IM VoiceTyper.exe /F >nul 2>&1
echo [2/4] 備份舊版...
if exist dist\VoiceTyper (
  if exist dist\VoiceTyper-prev rmdir /s /q dist\VoiceTyper-prev
  ren dist\VoiceTyper VoiceTyper-prev
)
echo [3/4] PyInstaller 打包...
venv\Scripts\pyinstaller.exe voice_typer.spec --noconfirm || (echo 打包失敗 & pause & exit /b 1)
echo [4/4] 啟動新版...
start "" "dist\VoiceTyper\VoiceTyper.exe"
echo 完成。舊版保留在 dist\VoiceTyper-prev（確認新版正常後可刪）。
pause
