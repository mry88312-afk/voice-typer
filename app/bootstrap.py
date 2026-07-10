"""啟動流程：單一實例鎖 → 初始化資料 → 建 stores → onboarding → 跑 app。"""
import sys
import time
from dotenv import load_dotenv
import customtkinter as ctk

from app.paths import (
    ENV_FILE, CONFIG_FILE, HISTORY_FILE, USAGE_FILE, LEARNED_WORDS_FILE,
    ensure_user_data_initialized,
)
from app.runtime import log, show_message
from ui.theme import init_app_theme


def _is_first_run() -> bool:
    """是否真的首次安裝 (才顯示 onboarding)。

    重試 + 雙檔檢查，避免「開機/前一實例關閉瞬間，存在的檔案 .exists() 暫時回 False」
    這種假象觸發 onboarding (這正是之前『設定頁一直跳』的真兇)。
    只要 .env 或 config.json 任一個在任一次重試中存在 → 不是首次 → 不跳。
    """
    for attempt in range(5):
        try:
            if ENV_FILE.exists() or CONFIG_FILE.exists():
                return False
        except Exception:
            pass
        if attempt < 4:
            time.sleep(0.3)
    return True

_instance_mutex = None


def _acquire_single_instance() -> bool:
    """Windows mutex 確保只跑一個實例。回傳 False = 已有實例。
    必須用 WinDLL(use_last_error=True) + get_last_error()，否則 last error 會被覆蓋。"""
    global _instance_mutex
    try:
        import ctypes
        from ctypes import wintypes
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        _instance_mutex = kernel32.CreateMutexW(None, False, 'VoiceTyperSingleInstance')
        last_error = ctypes.get_last_error()
        if _instance_mutex == 0:
            return True
        return last_error != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def main():
    if not _acquire_single_instance():
        log.info('偵測到已有實例在執行，本次啟動直接結束')
        sys.exit(0)

    ensure_user_data_initialized()
    load_dotenv(ENV_FILE, override=True)

    # 健壯資料層
    from data.config import ConfigStore
    from data.env import EnvStore
    from data.profiles import ProfileStore
    from data.history import HistoryManager
    from data.usage import UsageManager
    from data.learned import LearnedWordsManager

    config = ConfigStore(CONFIG_FILE, logger=log)
    env = EnvStore(ENV_FILE, logger=log)
    history = HistoryManager(HISTORY_FILE)
    usage = UsageManager(USAGE_FILE)
    profiles = ProfileStore(config, logger=log)
    learned = LearnedWordsManager(LEARNED_WORDS_FILE)

    if config.degraded:
        log.warning('設定讀取失敗，本次以唯讀模式啟動 (不會覆蓋磁碟上的真實設定)')

    init_app_theme()
    root = ctk.CTk()
    root.withdraw()
    root.title('Voice Typer')

    # ── Onboarding 判斷 ──
    # 只看「.env 檔存不存在」這一個鐵硬的事實，不依賴 config / setup_completed /
    # .bak 備份 (那些在開機檔案鎖定時會誤判，是之前「設定頁一直跳」的真兇)。
    #   .env 存在  → 絕對不跳 onboarding (你已經設定過了)
    #   .env 不存在 → 真．首次安裝，才引導設定
    has_keys = env.has_any_key()
    need_onboarding = _is_first_run()
    log.info(f'啟動檢查：首次安裝={need_onboarding}, 有任何 key={has_keys}, '
             f'config 唯讀={config.degraded}')

    if need_onboarding:
        log.info('首次安裝 (.env 與 config.json 連續重試都不存在) → 顯示 Onboarding')
        try:
            from ui.onboarding import OnboardingWizard
            wizard = OnboardingWizard(root, env, config)
            root.wait_window(wizard)
            load_dotenv(ENV_FILE, override=True)
        except Exception as e:
            log.error(f'Onboarding 顯示失敗，略過直接進入主程式: {e}')
    elif not has_keys:
        # .env 在但讀不到 key (可能開機鎖檔閃失) → 不跳設定頁，進托盤待命
        log.info('.env 存在但暫時讀不到 key，直接進托盤 (可從設定補)')

    # 啟動主程式 (無論有沒有 key，一律進托盤)
    from app.application import VoiceTyperApp
    app = VoiceTyperApp(root, config, env, history, usage, profiles, learned)
    app.start()
