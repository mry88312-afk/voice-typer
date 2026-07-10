"""所有檔案/目錄路徑解析 + 首次啟動資料初始化。

資料一律存 %APPDATA%/VoiceTyper（frozen 與 source 皆同），避免「兩套資料世界」。
可用環境變數 VOICE_TYPER_DATA_DIR 覆寫（測試/可攜用途）。
"""
import os
import sys
from pathlib import Path


def _resolve_base_dir() -> Path:
    """使用者資料一律放 %APPDATA%/VoiceTyper — 不分 frozen / source。
    這樣 exe、python main.py、任何程式碼副本永遠共用同一份設定，
    根治「兩套資料世界」造成的 KEY/設定時有時無。
    可用環境變數 VOICE_TYPER_DATA_DIR 覆寫（測試/可攜用途）。"""
    override = os.environ.get('VOICE_TYPER_DATA_DIR')
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / 'VoiceTyper' if appdata else Path.home() / '.voice-typer'
    base.mkdir(parents=True, exist_ok=True)
    return base


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
