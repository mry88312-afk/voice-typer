"""通用 JSON 持久化 — 原子寫入、自動備份、讀取重試、失敗鎖寫。

設計目標 (根治舊版「開機讀取閃失 → 退回預設 → 下次存檔覆蓋真實資料」的崩潰鏈):

1. 讀取重試：開機磁碟忙 / 防毒鎖檔時，重試數次再放棄。
2. 失敗不退預設：讀不到就回 None + 進入 degraded(唯讀) 模式，
   呼叫端可自行決定 fallback，但 store 本身「絕不」在 degraded 模式寫檔。
3. 原子寫入：寫到 .tmp → flush+fsync → os.replace 原子覆蓋，
   寫到一半當機也不會留半殘檔。
4. 自動備份：每次成功寫入前，先把現有好檔複製成 .bak。
   主檔壞了 load() 會自動從 .bak 救回。
"""
import json
import os
import shutil
import time
from pathlib import Path


class JsonStore:
    def __init__(self, path, logger=None, retries=4, retry_delay=0.15):
        self.path = Path(path)
        self.bak_path = self.path.with_suffix(self.path.suffix + '.bak')
        self.tmp_path = self.path.with_suffix(self.path.suffix + '.tmp')
        self.logger = logger
        self.retries = retries
        self.retry_delay = retry_delay
        self.degraded = False   # True = 讀取失敗，禁止寫入以免覆蓋真實資料

    def _log(self, level, msg):
        if self.logger:
            try:
                getattr(self.logger, level)(f'[{self.path.name}] {msg}')
                return
            except Exception:
                pass
        print(f'[{self.path.name}] {msg}')

    def _read_file(self, p: Path):
        """讀單一檔案，帶重試。回傳 dict 或 raise。"""
        last_err = None
        for attempt in range(self.retries):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except FileNotFoundError:
                raise
            except Exception as e:
                last_err = e
                time.sleep(self.retry_delay)
        raise last_err if last_err else RuntimeError('read failed')

    def load(self, default=None):
        """載入。成功回 dict；主檔壞掉自動試 .bak；都失敗回 default 並進 degraded。

        關鍵：回 default 時 degraded=True，之後 save() 會被擋下，
        絕不會用 default 覆蓋掉磁碟上可能還在的真實檔案。
        """
        self.degraded = False

        if not self.path.exists():
            # 全新安裝，檔案還沒建立 → 用 default，但不算 degraded (可正常寫入)
            return default if default is not None else {}

        # 試主檔
        try:
            data = self._read_file(self.path)
            return data
        except FileNotFoundError:
            return default if default is not None else {}
        except Exception as e:
            self._log('warning', f'主檔讀取失敗: {e}，嘗試 .bak')

        # 試備份
        if self.bak_path.exists():
            try:
                data = self._read_file(self.bak_path)
                self._log('info', '已從 .bak 救回資料')
                # 把好的 .bak 寫回主檔
                try:
                    shutil.copy(str(self.bak_path), str(self.path))
                except Exception:
                    pass
                return data
            except Exception as e:
                self._log('error', f'.bak 也讀取失敗: {e}')

        # 主檔與備份都救不回 → degraded，禁止寫入
        self.degraded = True
        self._log('error', '主檔與備份都無法讀取，進入唯讀模式 (本次不會寫檔，保護現有資料)')
        return default if default is not None else {}

    def save(self, data: dict) -> bool:
        """原子寫入 + 備份輪替。degraded 模式下拒絕寫入。回傳是否成功。"""
        if self.degraded:
            self._log('warning', '唯讀模式中，拒絕寫入 (避免覆蓋真實資料)')
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 1. 先備份現有好檔
            if self.path.exists():
                try:
                    shutil.copy(str(self.path), str(self.bak_path))
                except Exception as e:
                    self._log('warning', f'備份失敗 (繼續寫入): {e}')
            # 2. 寫到 tmp + flush + fsync
            with open(self.tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # 3. 原子覆蓋
            os.replace(str(self.tmp_path), str(self.path))
            return True
        except Exception as e:
            self._log('error', f'寫入失敗: {e}')
            try:
                if self.tmp_path.exists():
                    self.tmp_path.unlink()
            except Exception:
                pass
            return False
