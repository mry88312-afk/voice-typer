"""執行期共用工具：logger、訊息框、致命錯誤。"""
import sys
import logging
from logging.handlers import RotatingFileHandler

from app.paths import LOG_FILE


def _setup_logger():
    logger = logging.getLogger('voice_typer')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    # delay=True：第一次寫入時才開檔，避開啟動瞬間 log 檔被前一實例鎖住的 race
    fh = RotatingFileHandler(LOG_FILE, encoding='utf-8', maxBytes=1024 * 1024,
                             backupCount=2, delay=True)
    fh.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(fh)
    try:
        if sys.stdout is not None and sys.stdout.isatty():
            ch = logging.StreamHandler(sys.stdout)
            ch.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(ch)
    except Exception:
        pass
    return logger


log = _setup_logger()


def show_message(title, text, error=True):
    try:
        import ctypes
        flag = (0x10 if error else 0x40) | 0x40000 | 0x10000
        ctypes.windll.user32.MessageBoxW(0, text, title, flag)
    except Exception:
        log.info(f"{title}: {text}")


def fatal(title, text):
    log.error(f"{title}: {text}")
    show_message(title, text, error=True)
    sys.exit(1)


def boot_stage(name: str):
    """寫入啟動階段麵包屑（覆寫式、絕不拋錯）。卡死時看這個檔就知道卡在哪一步。"""
    try:
        from app.paths import BASE_DIR
        import time as _t
        (BASE_DIR / 'boot-stage.txt').write_text(
            f'{name} {_t.strftime("%Y-%m-%d %H:%M:%S")}', encoding='utf-8')
    except Exception:
        pass


def install_global_excepthooks():
    """背景 thread 與 tk callback 的未捕捉例外 → 寫進 log（原本會無聲消失）。"""
    import threading
    def _th_hook(args):
        log.error('thread 未捕捉例外',
                   exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _th_hook
