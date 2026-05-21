"""Profile (情境/模式) 管理 — 每個 profile 有獨立的詞典與潤色 prompt"""
from typing import Optional


# 4 個內建預設 profile
DEFAULT_PROFILES = [
    {
        'id': 'default',
        'name': '一般輸入',
        'description': '日常打字替代 — 口語整理為通順書面語',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            '請將以下語音轉錄結果整理成通順的書面語。要求：\n'
            '1. 修正錯字、補上完整的中文標點符號（句號、逗號、問號）\n'
            '2. 簡體字改為繁體字\n'
            '3. 移除重複的口語贅詞（嗯、那個、就是等）\n'
            '4. 保留原意，不要擅自加入內容\n'
            '5. 直接輸出整理後的文字，不要加任何說明：'
        ),
    },
    {
        'id': 'copywriting',
        'name': '文案撰寫',
        'description': '行銷文案、社群貼文、廣告標語',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            '請將以下語音口述改寫成吸引人的繁體中文行銷文案。要求：\n'
            '1. 加強情緒張力、加入吸引讀者的開頭\n'
            '2. 句子簡短有力，適合社群媒體閱讀\n'
            '3. 補上完整標點符號，必要時分段\n'
            '4. 可適度加入 emoji（最多 2-3 個）\n'
            '5. 保留核心訊息，但語氣要更生動\n'
            '6. 直接輸出文案，不要加任何說明：'
        ),
    },
    {
        'id': 'email',
        'name': 'Email 撰寫',
        'description': '商務 email — 禮貌、專業、結構清楚',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            '請將以下語音口述改寫成正式的繁體中文商務 email 內容。要求：\n'
            '1. 使用禮貌、專業的口吻（您好、敬請、感謝等）\n'
            '2. 結構清楚：開頭問候、正文、結尾敬語\n'
            '3. 補上完整標點符號，適當分段\n'
            '4. 移除口語化用詞\n'
            '5. 保留所有原意與細節\n'
            '6. 不需要加主旨、稱謂、署名，只輸出 email 內文：'
        ),
    },
    {
        'id': 'code',
        'name': 'Commit (英文)',
        'description': '⚠️ 會把中文翻成英文 commit message',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            'Convert the following Chinese voice input into a concise English '
            'commit message or bug report. Requirements:\n'
            '1. Use imperative mood (Add / Fix / Refactor / Remove ...)\n'
            '2. Keep it under 72 chars for commit subject; full description on new lines\n'
            '3. Be technical and precise\n'
            '4. Preserve technical terms in English (API names, error codes, etc.)\n'
            '5. Output the message only, no explanation:'
        ),
    },
    {
        'id': 'translate_en',
        'name': '翻譯 (中→英)',
        'description': '把中文口述翻譯成英文',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            '請將以下中文口述翻譯成自然流暢的英文。要求：\n'
            '1. 保持原意，不要意譯過頭\n'
            '2. 使用正確的標點符號\n'
            '3. 若有專有名詞、人名、產品名，保留原樣或用業界常用譯名\n'
            '4. 直接輸出英文翻譯，不要加任何說明：'
        ),
    },
    {
        'id': 'custom',
        'name': '自訂',
        'description': '空白範本 — 在「設定 → 情境」自由編輯 prompt',
        'vocabulary': [],
        'enhance_enabled': True,
        'enhance_prompt': (
            '請整理以下文字，補上適當的繁體中文標點符號，'
            '簡體字改為繁體字，移除口語贅詞。直接輸出整理後的文字：'
        ),
    },
]


# 預設 provider 設定
DEFAULT_TRANSCRIBER = {
    'provider': 'openai',
    'model': 'whisper-1',
}

DEFAULT_ENHANCER = {
    'provider': 'anthropic',
    'model': 'claude-haiku-4-5-20251001',
}


class ProfileManager:
    """讀寫 profiles，內含 active profile 管理"""

    def __init__(self, config_mgr):
        self.config_mgr = config_mgr
        self._ensure_initialized()

    def _ensure_initialized(self):
        """確保 config 內有 profiles 結構 (新舊 config 兼容)"""
        profiles = self.config_mgr.get('profiles')
        if not profiles:
            # 從舊 config 遷移
            self._migrate_from_legacy()
        else:
            # 已有 profiles → 補上新版加入的內建 profile (例如自訂、翻譯)
            self._sync_default_profiles()

    def _sync_default_profiles(self):
        """確保 DEFAULT_PROFILES 中每個 id 都存在 (新版加的自動補)"""
        existing = list(self.all())
        existing_ids = {p.get('id') for p in existing}
        changed = False
        for default_p in DEFAULT_PROFILES:
            if default_p['id'] not in existing_ids:
                existing.append(dict(default_p))
                changed = True
        if changed:
            self.config_mgr.set('profiles', existing)
            self.config_mgr.save()

    def _migrate_from_legacy(self):
        """把舊版 config 中的 vocabulary / enhance_prompt 遷移到 default profile"""
        legacy_vocab = self.config_mgr.get('vocabulary') or []
        legacy_enhance = self.config_mgr.get('enable_ai_enhance', False)
        legacy_prompt = self.config_mgr.get('ai_enhance_prompt')

        profiles = []
        for p in DEFAULT_PROFILES:
            new_p = dict(p)
            # 把舊的設定灌到 default profile
            if p['id'] == 'default':
                if legacy_vocab:
                    new_p['vocabulary'] = list(legacy_vocab)
                new_p['enhance_enabled'] = bool(legacy_enhance) or True
                if legacy_prompt and '請將以下口語' in legacy_prompt:
                    # 舊預設 prompt → 用新的 default
                    pass
                elif legacy_prompt:
                    new_p['enhance_prompt'] = legacy_prompt
            profiles.append(new_p)

        self.config_mgr.set('profiles', profiles)
        self.config_mgr.set('active_profile_id', 'default')

        # 確保 transcriber / enhancer config 存在
        if not self.config_mgr.get('transcriber'):
            self.config_mgr.set('transcriber', dict(DEFAULT_TRANSCRIBER))
        if not self.config_mgr.get('enhancer'):
            self.config_mgr.set('enhancer', dict(DEFAULT_ENHANCER))

        self.config_mgr.save()

    # ---------- API ----------
    def all(self) -> list[dict]:
        return list(self.config_mgr.get('profiles') or [])

    def get(self, profile_id: str) -> Optional[dict]:
        for p in self.all():
            if p.get('id') == profile_id:
                return p
        return None

    def active(self) -> dict:
        active_id = self.config_mgr.get('active_profile_id', 'default')
        p = self.get(active_id)
        if p:
            return p
        # fallback: 第一個 profile
        all_p = self.all()
        return all_p[0] if all_p else DEFAULT_PROFILES[0]

    def set_active(self, profile_id: str):
        if self.get(profile_id):
            self.config_mgr.set('active_profile_id', profile_id)
            self.config_mgr.save()

    def update(self, profile_id: str, **fields):
        profiles = self.all()
        for i, p in enumerate(profiles):
            if p.get('id') == profile_id:
                profiles[i] = {**p, **fields}
                break
        self.config_mgr.set('profiles', profiles)
        self.config_mgr.save()

    def add(self, profile: dict):
        profiles = self.all()
        profiles.append(profile)
        self.config_mgr.set('profiles', profiles)
        self.config_mgr.save()

    def remove(self, profile_id: str):
        if profile_id == 'default':
            return  # default 不能刪
        profiles = [p for p in self.all() if p.get('id') != profile_id]
        self.config_mgr.set('profiles', profiles)
        # 如果刪掉的是 active，切回 default
        if self.config_mgr.get('active_profile_id') == profile_id:
            self.config_mgr.set('active_profile_id', 'default')
        self.config_mgr.save()
