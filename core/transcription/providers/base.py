"""Provider 抽象介面 + 註冊表。

provider 類別自我註冊到 TRANSCRIBER_PROVIDERS / ENHANCER_PROVIDERS。
顯示用的 metadata (名稱、定價) 另由 resources/providers.json 提供。
"""
from abc import ABC, abstractmethod


class TranscriberBase(ABC):
    provider_id: str = ''
    model: str = ''
    api_key_env: str = ''

    def __init__(self, api_key: str, language: str = 'auto', prompt: str = ''):
        self.api_key = api_key
        self.language = language
        self.prompt = prompt or ''

    @abstractmethod
    def transcribe(self, audio_file_path: str) -> dict:
        raise NotImplementedError


class EnhancerBase(ABC):
    provider_id: str = ''
    model: str = ''
    api_key_env: str = ''

    def __init__(self, api_key: str, prompt: str = '', model: str = None):
        self.api_key = api_key
        self.prompt = prompt or ''
        if model:
            self.model = model

    @abstractmethod
    def enhance(self, text: str) -> dict:
        raise NotImplementedError


TRANSCRIBER_PROVIDERS = {}
ENHANCER_PROVIDERS = {}


def register_transcriber(provider_id, display_name, models, cls,
                         api_key_env, api_key_help_url=''):
    TRANSCRIBER_PROVIDERS[provider_id] = {
        'id': provider_id, 'display_name': display_name, 'models': models,
        'class': cls, 'api_key_env': api_key_env, 'api_key_help_url': api_key_help_url,
    }


def register_enhancer(provider_id, display_name, models, cls,
                      api_key_env, api_key_help_url=''):
    ENHANCER_PROVIDERS[provider_id] = {
        'id': provider_id, 'display_name': display_name, 'models': models,
        'class': cls, 'api_key_env': api_key_env, 'api_key_help_url': api_key_help_url,
    }


def get_transcriber(provider_id, api_key, model=None, language='auto', prompt=''):
    if provider_id not in TRANSCRIBER_PROVIDERS:
        raise ValueError(f'未知的 transcriber provider: {provider_id}')
    cls = TRANSCRIBER_PROVIDERS[provider_id]['class']
    inst = cls(api_key=api_key, language=language, prompt=prompt)
    if model:
        inst.model = model
    return inst


def get_enhancer(provider_id, api_key, model=None, prompt=''):
    if provider_id not in ENHANCER_PROVIDERS:
        raise ValueError(f'未知的 enhancer provider: {provider_id}')
    cls = ENHANCER_PROVIDERS[provider_id]['class']
    return cls(api_key=api_key, prompt=prompt, model=model)
