"""ConfigStore — 使用者設定，建在健壯的 JsonStore 之上。

跟舊版 ConfigManager 的關鍵差異：
- 讀取失敗時「不會」退回預設值再覆蓋真實檔案 (degraded 模式擋寫入)。
- 缺漏欄位用 default_config 補齊，但只在記憶體補，不污染磁碟。
- setup_completed 等狀態安全保存。
"""
from data.store import JsonStore
from data import resources


class ConfigStore:
    def __init__(self, path, logger=None):
        self._store = JsonStore(path, logger=logger)
        self._logger = logger
        self._listeners = []
        self._defaults = resources.default_config()
        self._data = {}
        self.load()

    def load(self):
        loaded = self._store.load(default=None)
        if loaded is None or self._store.degraded:
            # 讀取失敗 → 記憶體用預設，但 store 已進 degraded，不會寫回磁碟
            self._data = dict(self._defaults)
            self._degraded = True
        else:
            # 預設值補齊缺漏欄位 (只在記憶體)
            self._data = {**self._defaults, **loaded}
            self._degraded = False

    @property
    def degraded(self) -> bool:
        return getattr(self, '_degraded', False) or self._store.degraded

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def update(self, **kwargs):
        self._data.update(kwargs)

    def all(self) -> dict:
        return dict(self._data)

    def save(self) -> bool:
        ok = self._store.save(self._data)
        if ok:
            for cb in self._listeners:
                try:
                    cb(self._data)
                except Exception as e:
                    if self._logger:
                        self._logger.error(f'config listener error: {e}')
        return ok

    def subscribe(self, callback):
        self._listeners.append(callback)
