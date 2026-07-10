"""自學詞典 — 從 Whisper vs Claude 潤色差異中偷學使用者的「真正」詞彙

核心邏輯：
- 每次轉錄都記錄 (raw_from_whisper, enhanced_by_claude)
- 找出 Claude 修改的「詞」(例如 Whisper 寫「累積」→ Claude 改成「Ragic」)
- 累計同一個修正出現次數 → 達到閾值就建議加入詞典
- 使用者可以一鍵接受 / 永久忽略
"""
import json
import re
import time
from pathlib import Path
from typing import Optional


# 建議閾值：同個修正出現 N 次才提示
SUGGEST_THRESHOLD = 2

# 詞長度範圍
MIN_WORD_LEN = 2
MAX_WORD_LEN = 12


class LearnedWordsManager:
    """偷學使用者實際用的詞彙"""

    def __init__(self, path: Path):
        self.path = path
        self._data = {
            'suggestions': {},  # {claude_word: {whisper_form, count, last_seen, profile_ids}}
            'accepted': [],     # 已接受加到某個 profile 的詞
            'ignored': [],      # 永久忽略的詞
        }
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception:
                pass
        # 確保結構完整
        self._data.setdefault('suggestions', {})
        self._data.setdefault('accepted', [])
        self._data.setdefault('ignored', [])

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"learned words save failed: {e}")

    def analyze(self, raw: str, enhanced: str, profile_id: str = 'default'):
        """比對 Whisper 跟 Claude 結果，找出修改的詞並累計"""
        if not raw or not enhanced or raw == enhanced:
            return []

        diffs = self._find_word_diffs(raw, enhanced)
        new_suggestions = []
        for whisper_form, claude_form in diffs:
            # 已被使用者接受或忽略 → 跳過
            if claude_form in self._data['accepted'] or claude_form in self._data['ignored']:
                continue
            # 太短或太長 → 跳過
            if not (MIN_WORD_LEN <= len(claude_form) <= MAX_WORD_LEN):
                continue
            # 純標點/數字 → 跳過
            if not self._is_meaningful(claude_form):
                continue

            entry = self._data['suggestions'].setdefault(claude_form, {
                'whisper_form': whisper_form,
                'count': 0,
                'first_seen': time.time(),
                'last_seen': time.time(),
                'profile_ids': [],
            })
            entry['count'] += 1
            entry['last_seen'] = time.time()
            entry['whisper_form'] = whisper_form  # 更新最新一次的 Whisper 寫法
            if profile_id not in entry['profile_ids']:
                entry['profile_ids'].append(profile_id)

            if entry['count'] >= SUGGEST_THRESHOLD:
                new_suggestions.append(claude_form)

        if diffs:
            self.save()
        return new_suggestions

    def _find_word_diffs(self, raw: str, enhanced: str) -> list:
        """找出 raw 跟 enhanced 中對應位置的不同「詞」

        策略：對齊兩個句子的字元，找出 enhanced 中存在但 raw 中沒有的「詞」。
        簡單版：把兩段文字切成詞 (用標點分段)，跑 difflib 找替換。
        """
        try:
            import difflib
        except ImportError:
            return []

        # 用簡單規則切詞：中文按字符 + 英文/數字按空白切
        raw_tokens = self._tokenize(raw)
        enh_tokens = self._tokenize(enhanced)

        diffs = []
        sm = difflib.SequenceMatcher(None, raw_tokens, enh_tokens)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'replace':
                whisper_part = ''.join(raw_tokens[i1:i2])
                claude_part = ''.join(enh_tokens[j1:j2])
                # 太短的替換通常是錯字校正，但專有名詞通常 2-6 字
                if 2 <= len(claude_part) <= 12 and whisper_part != claude_part:
                    diffs.append((whisper_part, claude_part))
        return diffs

    def _tokenize(self, text: str) -> list:
        """中英文混合切詞：中文一字一 token、英文/數字連續一 token"""
        tokens = []
        buf = []
        for ch in text:
            if ch.isspace() or self._is_punct(ch):
                if buf:
                    tokens.append(''.join(buf))
                    buf = []
            elif self._is_cjk(ch):
                if buf:
                    tokens.append(''.join(buf))
                    buf = []
                tokens.append(ch)
            else:
                buf.append(ch)
        if buf:
            tokens.append(''.join(buf))
        return tokens

    @staticmethod
    def _is_cjk(ch: str) -> bool:
        return '一' <= ch <= '鿿'

    @staticmethod
    def _is_punct(ch: str) -> bool:
        return ch in '，。、；：？！「」『』（）()【】〈〉《》""\'\'.,;:?!()[]{}<>/-_*'

    def _is_meaningful(self, word: str) -> bool:
        if not word:
            return False
        # 純標點/空白
        if all(self._is_punct(c) or c.isspace() for c in word):
            return False
        # 純數字
        if word.isdigit():
            return False
        # 太多空格
        if word.count(' ') > 2:
            return False
        return True

    # ---------- 公開 API ----------
    def top_suggestions(self, limit: int = 20) -> list:
        """回傳建議列表 (按 count 由多到少)"""
        items = []
        for word, entry in self._data['suggestions'].items():
            if entry['count'] >= SUGGEST_THRESHOLD:
                items.append({
                    'word': word,
                    'whisper_form': entry.get('whisper_form', ''),
                    'count': entry['count'],
                    'last_seen': entry.get('last_seen', 0),
                    'profile_ids': entry.get('profile_ids', []),
                })
        items.sort(key=lambda x: (-x['count'], -x['last_seen']))
        return items[:limit]

    def all_suggestions(self) -> list:
        """所有建議 (不過閾值)"""
        return list(self._data['suggestions'].keys())

    def accept(self, word: str):
        """使用者接受 → 加到 accepted、從 suggestions 移除"""
        if word not in self._data['accepted']:
            self._data['accepted'].append(word)
        self._data['suggestions'].pop(word, None)
        self.save()

    def ignore(self, word: str):
        """使用者永久忽略"""
        if word not in self._data['ignored']:
            self._data['ignored'].append(word)
        self._data['suggestions'].pop(word, None)
        self.save()

    def reset_word(self, word: str):
        """重置：讓某個詞再次被建議"""
        if word in self._data['accepted']:
            self._data['accepted'].remove(word)
        if word in self._data['ignored']:
            self._data['ignored'].remove(word)
        self.save()

    def clear_all(self):
        self._data = {'suggestions': {}, 'accepted': [], 'ignored': []}
        self.save()

    def stats(self) -> dict:
        return {
            'suggestions_total': len(self._data['suggestions']),
            'suggestions_ready': len(self.top_suggestions(limit=999)),
            'accepted_total': len(self._data['accepted']),
            'ignored_total': len(self._data['ignored']),
        }
