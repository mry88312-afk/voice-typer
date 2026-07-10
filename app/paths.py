"""所有檔案/目錄路徑解析 + 首次啟動資料初始化。

frozen (.exe): 資料存 %APPDATA%/VoiceTyper (避免 PyInstaller temp dir 重啟消失)
source (python): 存專案根目錄
"""
import os
import sys
from pathlib import Path


def _resolve_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / 'VoiceTyper' if appdata else Path.home() / '.voice-typer'
        base.mkdir(parents=True, exist_ok=True)
        return base
    # app/paths.py → 專案根
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_base_dir()
BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

LOG_FILE = BASE_DIR / 'voice-typer.log'
CONFIG_FILE = BASE_DIR / 'config.json'
ENV_FILE = BASE_DIR / '.env'
HISTORY_FILE = BASE_DIR / 'history.json'
USAGE_FILE = BASE_DIR / 'usage.json'
LEARNED_WORDS_FILE = BASE_DIR / 'learned_words.json'
RECORDINGS_DIR = BASE_DIR / 'recordings'


def ensure_user_data_initialized():
    """首次啟動準備。設定預設值由 resources 提供，這裡只建目錄 + 複製 .env 範本參考。"""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    # .env.example 給使用者參考
    example_dst = BASE_DIR / '.env.example'
    if not example_dst.exists():
        src = BUNDLE_DIR / '.env.example'
        if src.exists():
            try:
                import shutil
                shutil.copy(str(src), str(example_dst))
            except Exception:
                pass
