"""歷史紀錄 JSON 儲存"""
import json
import time
from pathlib import Path
from typing import List


MAX_HISTORY = 100


class HistoryManager:
    def __init__(self, history_path: Path, max_records: int = MAX_HISTORY):
        self.path = history_path
        self.max = max_records
        self._records: list[dict] = []
        self.load()

    def load(self):
        if not self.path.exists():
            self._records = []
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self._records = json.load(f)
        except Exception:
            self._records = []

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"history save failed: {e}")

    def add(self, raw: str, enhanced: str | None = None, language: str = 'zh',
            transcriber_provider: str = None, transcriber_model: str = None,
            enhancer_provider: str = None, enhancer_model: str = None,
            profile_id: str = None, profile_name: str = None):
        """新增一筆轉錄記錄 (含使用的 AI 模型資訊)"""
        record = {
            'ts': time.time(),
            'raw': raw,
            'enhanced': enhanced,
            'language': language,
            'transcriber_provider': transcriber_provider,
            'transcriber_model': transcriber_model,
            'enhancer_provider': enhancer_provider,
            'enhancer_model': enhancer_model,
            'profile_id': profile_id,
            'profile_name': profile_name,
        }
        self._records.insert(0, record)
        if len(self._records) > self.max:
            self._records = self._records[:self.max]
        self.save()

    def all(self) -> List[dict]:
        return list(self._records)

    def search(self, query: str) -> List[dict]:
        if not query:
            return self.all()
        q = query.lower()
        return [
            r for r in self._records
            if q in (r.get('raw') or '').lower()
            or q in (r.get('enhanced') or '').lower()
        ]

    def remove(self, index: int):
        if 0 <= index < len(self._records):
            del self._records[index]
            self.save()

    def clear(self):
        self._records = []
        self.save()
