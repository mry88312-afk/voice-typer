"""Whisper 幻覺過濾 — 黑名單從 resources/hallucinations.json 載入，不寫死。"""
from data import resources

_cache = None


def _data():
    global _cache
    if _cache is None:
        _cache = resources.hallucinations()
    return _cache


def _normalize(s: str) -> str:
    """只留英數 + 中日韓字 (小寫)，去掉標點/空白/符號。"""
    return ''.join(c for c in s.lower() if c.isalnum() or '一' <= c <= '鿿')


def is_hallucination(text: str) -> bool:
    if not text:
        return False
    data = _data()
    blacklist = data.get('blacklist', [])
    short_max = data.get('short_max_len', 8)

    normalized = _normalize(text)
    if not normalized:
        return True

    # 黑名單比對：兩邊都正規化後比。跳過正規化後為空的項目
    # (例如 "......" 正規化成空字串，否則 "" in normalized 會永遠成立，
    #  害每一句話都被誤判成幻覺 — 這是之前「辨識完沒出字」的真兇)
    for b in blacklist:
        nb = _normalize(b)
        if nb and nb in normalized:
            return True

    # 太短 (<= short_max) 且完全沒中文字 → 視為雜訊幻覺
    if len(normalized) <= short_max:
        cjk = sum(1 for c in normalized if '一' <= c <= '鿿')
        if cjk == 0:
            return True
    return False
