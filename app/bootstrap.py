"""啟動流程：單一實例鎖 → 初始化資料 → 建 stores → onboarding → 跑 app。"""
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import customtkinter as ctk

from app.paths import (
    ENV_FILE, CONFIG_FILE, HISTORY_FILE, USAGE_FILE, LEARNED_WORDS_FILE,
    ensure_user_data_initialized,
)
from app.runtime import log, show_message, boot_stage, install_global_excepthooks
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


def _takeover_zombie_instance() -> bool:
    """舊實例握著 mutex 但沒心跳 → 判定殭屍，殺掉接管。
    回傳 True = 已接管可繼續啟動；False = 對方活得好好的。"""
    import os, time
    from app.paths import BASE_DIR
    try:
        import psutil
    except Exception:
        return False    # 沒有 psutil 就不冒險殺程序
    try:
        hb = BASE_DIR / 'heartbeat.txt'
        hb_age = None
        if hb.exists():
            hb_age = time.time() - float(hb.read_text(encoding='utf-8').strip() or 0)
        if hb_age is not None and hb_age < 60:
            return False            # 心跳新鮮 → 真的在跑
        pid_file = BASE_DIR / 'voice-typer.pid'
        if not pid_file.exists():
            return False            # 不知道 PID，不冒險
        pid = int(pid_file.read_text(encoding='utf-8').strip())
        if pid == os.getpid():
            return False
        p = psutil.Process(pid)
        name = p.name().lower()
        if not any(s in name for s in ('voicetyper', 'python')):
            return False            # PID 已被別的程式重用
        if time.time() - p.create_time() < 90:
            return False            # 對方剛啟動（可能還在初始化），給它時間
        p.kill()
        p.wait(timeout=10)
        time.sleep(1)
        return True                 # 我們手上的 mutex handle 仍有效，直接繼續啟動
    except Exception:
        return False


def main():
    # 上次啟動若沒走到 tray-ready，把卡點寫進 log（開機卡死的鐵證）
    try:
        _prev = (Path(str(ENV_FILE)).parent / 'boot-stage.txt')
        if _prev.exists():
            _s = _prev.read_text(encoding='utf-8').strip()
            if _s and not _s.startswith('tray-ready'):
                log.warning(f'上次啟動未完成，卡在階段: {_s}')
    except Exception:
        pass
    boot_stage('start')
    install_global_excepthooks()

    if not _acquire_single_instance():
        if _takeover_zombie_instance():
            log.warning('偵測到前一個實例無心跳（殭屍），已強制接管重啟')
        else:
            log.info('偵測到已有實例在執行且心跳正常，本次啟動結束')
            show_message(
                'Voice Typer',
                'Voice Typer 已經在執行中（右下角托盤）。\n\n'
                '如需重開：托盤圖示右鍵 → 重新啟動。',
                error=False,
            )
            sys.exit(0)
    boot_stage('mutex-ok')

    # 開機看門狗：從這一刻起，時限內必須進到 mainloop 心跳，否則自我重啟。
    # 放在 mutex 之後才啟動：第二實例的「已在執行中」訊息框會等使用者，不能被誤判。
    from app import watchdog
    watchdog.start()

    ensure_user_data_initialized()
    load_dotenv(ENV_FILE, override=True)
    boot_stage('data-init')

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
    boot_stage('stores-ready')

    from ui.theme import init_ctk_default_font
    init_app_theme()          # 只設外觀模式/色系（不碰字型、不需要 root）
    boot_stage('theme-ok')
    root = ctk.CTk()
    init_ctk_default_font()   # root 已存在，字型偵測安全
    def _tk_error(exc, val, tb):
        log.error('tk callback 例外', exc_info=(exc, val, tb))
    root.report_callback_exception = _tk_error
    boot_stage('tk-root-ok')
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
    boot_stage('onboarding-checked')

    if need_onboarding:
        log.info('首次安裝 (.env 與 config.json 連續重試都不存在) → 顯示 Onboarding')
        try:
            from ui.onboarding import OnboardingWizard
            watchdog.pause()    # 使用者填 key 沒有時限，暫停看門狗計時
            wizard = OnboardingWizard(root, env, config)
            root.wait_window(wizard)
            load_dotenv(ENV_FILE, override=True)
        except Exception as e:
            log.error(f'Onboarding 顯示失敗，略過直接進入主程式: {e}')
        finally:
            watchdog.resume()
    elif not has_keys:
        # .env 在但讀不到 key (可能開機鎖檔閃失) → 不跳設定頁，進托盤待命
        log.info('.env 存在但暫時讀不到 key，直接進托盤 (可從設定補)')

    # 啟動主程式 (無論有沒有 key，一律進托盤)
    from app.application import VoiceTyperApp
    app = VoiceTyperApp(root, config, env, history, usage, profiles, learned)
    boot_stage('app-starting')
    app.start()
