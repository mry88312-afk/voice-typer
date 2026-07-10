"""ProfileStore — 情境 (profile) 管理。預設情境從 resources/default_profiles.json 載入，
不再寫死在程式裡。加情境 = 改 JSON 或在 UI 新增。"""
from data import resources


class ProfileStore:
    def __init__(self, config_store, logger=None):
        self.config = config_store
        self.logger = logger
        self._ensure_initialized()

    def _ensure_initialized(self):
        profiles = self.config.get('profiles')
        if not profiles:
            # config 沒有 profiles (全新或讀取退預設) → 注入預設
            self.config.set('profiles', resources.default_profiles())
            self.config.set('active_profile_id', 'default')
            self.config.save()
        else:
            # 補上新版新增的內建情境 (依 id 比對)
            existing_ids = {p.get('id') for p in profiles}
            changed = False
            for dp in resources.default_profiles():
                if dp['id'] not in existing_ids:
                    profiles.append(dp)
                    changed = True
            if changed:
                self.config.set('profiles', profiles)
                self.config.save()

    def all(self) -> list:
        return list(self.config.get('profiles') or [])

    def get(self, profile_id: str):
        for p in self.all():
            if p.get('id') == profile_id:
                return p
        return None

    def active(self) -> dict:
        active_id = self.config.get('active_profile_id', 'default')
        p = self.get(active_id)
        if p:
            return p
        all_p = self.all()
        return all_p[0] if all_p else resources.default_profiles()[0]

    def set_active(self, profile_id: str):
        if self.get(profile_id):
            self.config.set('active_profile_id', profile_id)
            self.config.save()

    def update(self, profile_id: str, **fields):
        profiles = self.all()
        for i, p in enumerate(profiles):
            if p.get('id') == profile_id:
                profiles[i] = {**p, **fields}
                break
        self.config.set('profiles', profiles)
        self.config.save()

    def add(self, profile: dict):
        profiles = self.all()
        profiles.append(profile)
        self.config.set('profiles', profiles)
        self.config.save()

    def delete(self, profile_id: str):
        profiles = [p for p in self.all() if p.get('id') != profile_id]
        self.config.set('profiles', profiles)
        if self.config.get('active_profile_id') == profile_id:
            self.config.set('active_profile_id', 'default')
        self.config.save()
