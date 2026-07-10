"""載入 resources/*.json 資料檔 (預設值、provider 定義、schema 等)。

支援兩種執行模式：
- 從原始碼跑：resources/ 在專案根目錄
- PyInstaller 打包：resources/ 被打包進 bundle (sys._MEIPASS)
"""
import json
import sys
from pathlib import Path
from functools import lru_cache


def _resources_dir() -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        # data/resources.py → 專案根 → resources/
        base = Path(__file__).resolve().parent.parent
    return base / 'resources'


@lru_cache(maxsize=None)
def load_resource(name: str) -> dict:
    """載入並快取一個 resource JSON。name 例如 'providers' / 'default_config'。"""
    path = _resources_dir() / f'{name}.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def default_config() -> dict:
    cfg = dict(load_resource('default_config'))
    cfg.pop('_comment', None)
    # 注入預設情境
    cfg['profiles'] = default_profiles()
    cfg.setdefault('setup_completed', False)
    return cfg


def default_profiles() -> list:
    import copy
    return copy.deepcopy(load_resource('default_profiles'))


def providers() -> dict:
    return load_resource('providers')


def hallucinations() -> dict:
    return load_resource('hallucinations')


def settings_schema() -> dict:
    return load_resource('settings_schema')
