"""HotkeyManager — 全域快捷鍵註冊，逐鍵容錯 + 定時自癒。

一個鍵壞掉不影響其他、不會讓 app 退出；可重複呼叫 register() 熱重載；
watchdog 定期重新註冊，修復睡眠喚醒後 hook 失效。
"""
import keyboard


class HotkeyManager:
    def __init__(self, tk_root, logger=None, on_failure=None):
        self.root = tk_root
        self.logger = logger
        self.on_failure = on_failure   # callback(failed_list) 給 UI 通知用
        self._bindings = []            # [(name, combo, callback), ...]
        self._watchdog_ms = 10 * 60 * 1000

    def _log(self, level, msg):
        if self.logger:
            try:
                getattr(self.logger, level)(msg)
                return
            except Exception:
                pass
        print(msg)

    def set_bindings(self, bindings):
        """bindings: list of (name, combo, callback)"""
        self._bindings = bindings

    def register(self):
        """(重新) 註冊全部快捷鍵。回傳是否全部成功。"""
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        failed = []
        for name, combo, callback in self._bindings:
            combo = (combo or '').strip()
            if not combo:
                self._log('warning', f'快捷鍵「{name}」未設定，略過')
                continue
            try:
                keyboard.add_hotkey(combo, callback)
                self._log('info', f'快捷鍵註冊: {name} = {combo}')
            except Exception as e:
                self._log('error', f'快捷鍵「{name}」({combo}) 註冊失敗: {e}')
                failed.append(f'{name} ({combo})')
        if failed and self.on_failure:
            try:
                self.on_failure(failed)
            except Exception:
                pass
        return not failed

    def start_watchdog(self):
        """啟動定時自癒 (10 分鐘後第一次)。"""
        self.root.after(self._watchdog_ms, self._tick)

    def _tick(self):
        try:
            self.register()
        except Exception as e:
            self._log('error', f'快捷鍵看門狗失敗: {e}')
        self.root.after(self._watchdog_ms, self._tick)
