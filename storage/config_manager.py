"""config.json 讀寫 + 監聽變更"""
import json
from pathlib import Path
from typing import Callable


DEFAULT_CONFIG = {
    # 快捷鍵
    'hotkey': 'ctrl+alt+space',
    'cancel_hotkey': 'ctrl+alt+x',
    'streaming_hotkey': 'ctrl+shift+l',
    # 辨識
    'language': 'zh',
    'input_device': '',   # 空 = 系統預設麥克風

    'whisper_prompt': '嗯，這是繁體中文的對話內容，會包含完整的標點符號。',
    # 後端 provider (新)
    'transcriber': {'provider': 'openai', 'model': 'whisper-1'},
    'enhancer': {'provider': 'anthropic', 'model': 'claude-haiku-4-5-20251001'},
    # Profiles (新)
    'profiles': [],         # 由 ProfileManager 初始化填入預設 4 個
    'active_profile_id': 'default',
    # 行為
    'auto_paste': True,
    'play_sound': True,
    'restore_clipboard': True,
    'show_waveform': True,
    'save_history': True,
    'use_speaker_diarization': False,   # 會議錄音聲紋分離 (需 Google API Key)
    'theme': 'system',
    'first_run': False,
    # 舊版相容 (將由 profile 取代)
    'vocabulary': [],
    'enable_ai_enhance': False,
    'ai_enhance_prompt': (
        '請將以下口語化的文字整理為通順的書面語，保持原意，'
        '不要添加額外內容，使用繁體中文，直接輸出整理後的文字：'
    ),
}


class ConfigManager:
    def __init__(self, config_path: Path):
        self.path = config_path
        self._data = {}
        self._listeners: list[Callable[[dict], None]] = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
            except Exception:
                loaded = {}
        else:
            loaded = {}
        # 合併預設值
        self._data = {**DEFAULT_CONFIG, **loaded}

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        # 通知 listeners
        for cb in self._listeners:
            try:
                cb(self._data)
            except Exception as e:
                print(f"config listener error: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def update(self, **kwargs):
        self._data.update(kwargs)

    def all(self):
        return dict(self._data)

    def subscribe(self, callback: Callable[[dict], None]):
        """訂閱 config 變更，save 時會自動呼叫 callback"""
        self._listeners.append(callback)
