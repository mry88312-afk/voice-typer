"""EnvStore — 安全讀寫 .env (API keys)。帶讀取重試 + 原子寫入 + 保留註解。"""
import os
import re
import time
from pathlib import Path

_LINE_RE = re.compile(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$')


class EnvStore:
    def __init__(self, path, logger=None, retries=8, retry_delay=0.25):
        self.path = Path(path)
        self.tmp_path = self.path.parent / (self.path.name + '.tmp')
        self.logger = logger
        self.retries = retries
        self.retry_delay = retry_delay
        self._cache = None  # 最後一次成功讀到的內容；檔案被鎖的瞬間用它救場

    def _log(self, level, msg):
        if self.logger:
            try:
                getattr(self.logger, level)(f'[.env] {msg}')
                return
            except Exception:
                pass
        print(f'[.env] {msg}')

    def read(self) -> dict:
        """解析 .env，帶重試。讀不到回空 dict (不 raise，呼叫端不會崩)。

        注意：不能用 self.path.exists() 提前放棄 —— 開機/重開瞬間檔案被鎖
        (或防毒掃描) 時 exists() 會暫時回 False，直接 return {} 就是
        「金鑰尚未載入」一直跳的真兇。一律直接 open + 重試，
        FileNotFoundError 也視為暫時性錯誤；全失敗才 fallback 到快取。
        """
        last_err = None
        for attempt in range(self.retries):
            try:
                result = {}
                with open(self.path, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        m = _LINE_RE.match(line)
                        if m:
                            result[m.group(1)] = m.group(2).strip().strip('"').strip("'")
                self._cache = dict(result)
                return result
            except FileNotFoundError as e:
                last_err = e
                # 有快取 = 檔案剛剛還在，這是鎖檔假象 → 重試
                # 沒快取 + 連續 3 次真的找不到 → 視為真的不存在 (首次安裝)
                if self._cache is None and attempt >= 2:
                    return {}
            except Exception as e:
                last_err = e
            time.sleep(self.retry_delay)
        if self._cache is not None:
            self._log('warning', f'讀取失敗 ({last_err})，改用上次成功的快取')
            return dict(self._cache)
        self._log('warning', f'讀取失敗: {last_err}')
        return {}

    def get(self, key: str):
        v = self.read().get(key)
        if v:
            return v
        # 最後防線：bootstrap 的 load_dotenv 或 set() 已把 key 放進環境變數
        return os.environ.get(key) or None

    def set(self, key: str, value: str) -> bool:
        """更新單一 key，保留註解與順序，原子寫入。"""
        lines = []
        found = False
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped or stripped.startswith('#'):
                            lines.append(line)
                            continue
                        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', stripped)
                        if m and m.group(1) == key:
                            lines.append(f'{key}={value}\n')
                            found = True
                        else:
                            lines.append(line)
            except Exception as e:
                self._log('warning', f'讀取舊檔失敗，將重建: {e}')
                lines = []
        if not found:
            if lines and not lines[-1].endswith('\n'):
                lines.append('\n')
            lines.append(f'{key}={value}\n')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(self.tmp_path), str(self.path))
            os.environ[key] = value
            return True
        except Exception as e:
            self._log('error', f'寫入失敗: {e}')
            return False

    def is_valid(self, key: str, prefix: str = '') -> bool:
        v = self.get(key)
        if not v or 'your-' in v.lower():
            return False
        if prefix and not v.startswith(prefix):
            return False
        return True

    def has_any_key(self) -> bool:
        """是否有任何一把有效的 provider key (給 onboarding 判斷用)。"""
        data = self.read()
        for k in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
                  'GROQ_API_KEY', 'GOOGLE_API_KEY'):
            v = (data.get(k) or os.environ.get(k) or '').strip()
            if v and 'your-' not in v.lower():
                return True
        return False
