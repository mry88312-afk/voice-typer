"""開機/主迴圈看門狗：獨立 daemon thread，不依賴 logging、不依賴 tk。

針對兩種實戰發生過的卡死型態（2026-07-09、2026-07-25）：
1. 開機卡死：程序啟動後遲遲進不了 tk mainloop（登入瞬間 tk/字型初始化卡住）。
2. 主迴圈楔死：boot 階段全走完、托盤圖示都出來了，但 mainloop 從此一步不動
   —— heartbeat 一次都沒跳、log 一行都沒寫，快捷鍵撐幾分鐘後也跟著死。

為什麼不能靠既有的 _hotkey_watchdog / _state_watchdog：它們都掛在 root.after 上，
mainloop 死了它們就跟著死。本模組用純 threading + 直接檔案寫入，
連 logging 都不依賴（2026-07-25 案例中 logging 整場都寫不進檔案）。

自我重啟沿用 _restart() 的流程：釋放 mutex → 清 heartbeat/pid → 重生新程序 → os._exit。
防無限迴圈：30 分鐘內最多自動重啟 3 次，超過即自我停用並留下紀錄。
"""
import os
import sys
import time
import threading
import subprocess
from pathlib import Path

from app.paths import BASE_DIR, BUNDLE_DIR

# 時間參數（秒）
BOOT_DEADLINE = 180     # 從 start() 到 mainloop 第一次心跳的最長容忍時間
BEAT_STALE = 120        # mainloop 心跳（每 15s 一次）最長容忍靜默時間
POLL_INTERVAL = 5       # 看門狗輪詢間隔
SLEEP_GAP = 60          # 兩次輪詢之間 wall clock 差超過此值 → 判定系統剛睡醒，重置基準
RESTART_WINDOW = 1800   # 防迴圈統計視窗
RESTART_MAX = 3         # 視窗內最多自動重啟次數

WD_LOG = BASE_DIR / 'watchdog.log'
RESTART_LOG = BASE_DIR / 'watchdog-restarts.txt'

_lock = threading.Lock()
_started = False
_disabled = False
_paused = False
_boot_t0 = None         # monotonic：boot 計時起點
_last_beat = None       # monotonic：最後一次 mainloop 心跳；None = 還在 boot 階段
_stage = '?'


def _wlog(msg: str):
    """看門狗專用直寫 log，絕不拋錯、不經過 logging（logging 可能已死）。"""
    try:
        if WD_LOG.exists() and WD_LOG.stat().st_size > 256 * 1024:
            WD_LOG.unlink()
        with open(WD_LOG, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n')
    except Exception:
        pass


def notify_stage(name: str):
    """由 runtime.boot_stage() 轉呼叫，讓看門狗知道 boot 走到哪一步。"""
    global _stage
    _stage = name


def beat():
    """由 mainloop 的 _heartbeat_tick() 呼叫。第一次呼叫即代表 mainloop 已活著。"""
    global _last_beat
    with _lock:
        _last_beat = time.monotonic()


def pause():
    """進入需要使用者操作的長時間 UI（如 onboarding）前呼叫，暫停計時。"""
    global _paused
    with _lock:
        _paused = True
    _wlog('計時暫停（互動 UI）')


def resume():
    """互動 UI 結束後呼叫，重置計時基準再繼續監看。"""
    global _paused, _boot_t0, _last_beat
    with _lock:
        _paused = False
        now = time.monotonic()
        _boot_t0 = now
        if _last_beat is not None:
            _last_beat = now
    _wlog('計時恢復')


def disable(reason: str = ''):
    """正常退出/使用者主動重啟前呼叫，避免看門狗與退出流程賽跑。"""
    global _disabled
    _disabled = True
    _wlog(f'看門狗停用 ({reason})')


def _too_many_restarts() -> bool:
    """讀寫重啟紀錄檔；回傳 True = 短時間內重啟太多次，應放棄自動重啟。"""
    now = time.time()
    recent = []
    try:
        if RESTART_LOG.exists():
            for line in RESTART_LOG.read_text(encoding='utf-8').splitlines():
                try:
                    ts = float(line.strip())
                    if now - ts < RESTART_WINDOW:
                        recent.append(ts)
                except ValueError:
                    pass
    except Exception:
        pass
    if len(recent) >= RESTART_MAX:
        return True
    recent.append(now)
    try:
        RESTART_LOG.write_text('\n'.join(str(t) for t in recent), encoding='utf-8')
    except Exception:
        pass
    return False


def _self_restart(reason: str):
    """與 application._restart() 同款流程，但不碰任何可能已死的物件。"""
    _wlog(f'!! {reason} → 自我重啟')
    try:
        from app.runtime import log
        log.error(f'看門狗: {reason} → 自我重啟')   # best effort，logging 死了也無妨
    except Exception:
        pass
    if _too_many_restarts():
        _wlog(f'!! {RESTART_WINDOW // 60} 分鐘內已自動重啟 {RESTART_MAX} 次，放棄（避免無限迴圈）')
        disable('重啟次數達上限')
        return
    # 釋放單一實例 mutex，讓新程序拿得到
    try:
        import ctypes
        from app import bootstrap
        if getattr(bootstrap, '_instance_mutex', None):
            ctypes.windll.kernel32.CloseHandle(bootstrap._instance_mutex)
            bootstrap._instance_mutex = None
    except Exception:
        pass
    try:
        (BASE_DIR / 'heartbeat.txt').unlink(missing_ok=True)
        (BASE_DIR / 'voice-typer.pid').unlink(missing_ok=True)
    except Exception:
        pass
    try:
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable],
                             cwd=str(Path(sys.executable).parent))
        else:
            subprocess.Popen([sys.executable, str(BUNDLE_DIR / 'main.py')],
                             cwd=str(BUNDLE_DIR))
        _wlog('新程序已重生，本程序退出')
    except Exception as e:
        _wlog(f'重生失敗: {e}（本程序仍將退出，靠下次開機/手動啟動復活）')
    os._exit(86)


def _watch_loop():
    global _boot_t0, _last_beat
    last_poll_wall = time.time()
    while True:
        time.sleep(POLL_INTERVAL)
        now_wall = time.time()
        now = time.monotonic()
        with _lock:
            if _disabled:
                return
            # 系統睡眠喚醒：輪詢間隔被拉長 → 重置基準，給喚醒後的 mainloop 緩衝
            if now_wall - last_poll_wall > POLL_INTERVAL + SLEEP_GAP:
                _wlog(f'偵測到系統睡眠喚醒（輪詢間隔 {now_wall - last_poll_wall:.0f}s），重置計時')
                _boot_t0 = now
                if _last_beat is not None:
                    _last_beat = now
                last_poll_wall = now_wall
                continue
            last_poll_wall = now_wall
            if _paused:
                continue
            if _last_beat is None:
                # boot 階段：時限內必須看到 mainloop 第一次心跳
                if now - _boot_t0 > BOOT_DEADLINE:
                    stage = _stage
                    # 離開 lock 再重啟（_self_restart 不會回來）
                else:
                    continue
            else:
                if now - _last_beat > BEAT_STALE:
                    stage = _stage
                else:
                    continue
        # 走到這裡 = 超時，執行重啟（在 lock 外）
        if _last_beat is None:
            _self_restart(f'開機 {BOOT_DEADLINE}s 內未進入 mainloop（卡在階段: {stage}）')
        else:
            _self_restart(f'mainloop 心跳靜默超過 {BEAT_STALE}s（最後階段: {stage}）')
        return


def start():
    """啟動看門狗（冪等）。應在取得單一實例 mutex 之後立刻呼叫——
    太早呼叫會把「偵測到已有實例 → 等使用者按掉訊息框」誤判成開機卡死。"""
    global _started, _boot_t0
    with _lock:
        if _started:
            return
        _started = True
        _boot_t0 = time.monotonic()
    t = threading.Thread(target=_watch_loop, daemon=True, name='boot-watchdog')
    t.start()
    _wlog(f'看門狗啟動 (pid={os.getpid()}, boot期限={BOOT_DEADLINE}s, 心跳容忍={BEAT_STALE}s)')
