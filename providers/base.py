"""Provider 抽象介面 + 註冊表"""
from abc import ABC, abstractmethod


# ---------- Transcriber (語音 → 文字) ----------
class TranscriberBase(ABC):
    """轉錄器基底類別"""
    provider_id: str = ''
    model: str = ''
    api_key_env: str = ''

    def __init__(self, api_key: str, language: str = 'auto', prompt: str = ''):
        self.api_key = api_key
        self.language = language
        self.prompt = prompt or ''

    @abstractmethod
    def transcribe(self, audio_file_path: str) -> dict:
        """
        回傳 dict:
            text: str
            duration_seconds: float (用於 usage 計費)
            model: str
        """
        raise NotImplementedError


# ---------- Enhancer (文字 → 潤色文字) ----------
class EnhancerBase(ABC):
    """潤色器基底類別"""
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
        """
        回傳 dict:
            text: str
            input_tokens: int
            output_tokens: int
            model: str
        """
        raise NotImplementedError


# ---------- 註冊表 (在 import provider 時填入) ----------
TRANSCRIBER_PROVIDERS = {}   # { provider_id: { models: [...], class: ..., api_key_env: ... } }
ENHANCER_PROVIDERS = {}      # 同上


def register_transcriber(provider_id: str, display_name: str,
                          models: list, cls, api_key_env: str,
                          api_key_help_url: str = ''):
    TRANSCRIBER_PROVIDERS[provider_id] = {
        'id': provider_id,
        'display_name': display_name,
        'models': models,
        'class': cls,
        'api_key_env': api_key_env,
        'api_key_help_url': api_key_help_url,
    }


def register_enhancer(provider_id: str, display_name: str,
                       models: list, cls, api_key_env: str,
                       api_key_help_url: str = ''):
    ENHANCER_PROVIDERS[provider_id] = {
        'id': provider_id,
        'display_name': display_name,
        'models': models,
        'class': cls,
        'api_key_env': api_key_env,
        'api_key_help_url': api_key_help_url,
    }


def get_transcriber(provider_id: str, api_key: str,
                     model: str = None, language: str = 'auto',
                     prompt: str = '') -> TranscriberBase:
    if provider_id not in TRANSCRIBER_PROVIDERS:
        raise ValueError(f'未知的 transcriber provider: {provider_id}')
    info = TRANSCRIBER_PROVIDERS[provider_id]
    cls = info['class']
    instance = cls(api_key=api_key, language=language, prompt=prompt)
    if model:
        instance.model = model
    return instance


def get_enhancer(provider_id: str, api_key: str,
                  model: str = None, prompt: str = '') -> EnhancerBase:
    if provider_id not in ENHANCER_PROVIDERS:
        raise ValueError(f'未知的 enhancer provider: {provider_id}')
    info = ENHANCER_PROVIDERS[provider_id]
    cls = info['class']
    instance = cls(api_key=api_key, prompt=prompt, model=model)
    return instance


# 自動載入所有 provider modules (這樣 import providers 就會註冊)
def _load_all_providers():
    try:
        from providers import openai_provider  # noqa
    except Exception as e:
        print(f"failed to load openai_provider: {e}")
    try:
        from providers import anthropic_provider  # noqa
    except Exception as e:
        print(f"failed to load anthropic_provider: {e}")
    try:
        from providers import google_provider  # noqa
    except Exception as e:
        print(f"failed to load google_provider: {e}")
    try:
        from providers import groq_provider  # noqa
    except Exception as e:
        print(f"failed to load groq_provider: {e}")


_load_all_providers()
