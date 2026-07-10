"""載入全部 provider 並用 resources/providers.json 註冊。

providers.json 是 model 清單 + 顯示名稱的單一資料源；
這裡只負責把 JSON metadata 跟對應的 class 接起來。
加新 provider：1) 寫一個 *_provider.py 的 class  2) 在 providers.json 加一筆
                3) 在下面 _CLASS_MAP 對應上去
"""
from data import resources
from core.transcription.providers.base import (
    TranscriberBase, EnhancerBase,
    TRANSCRIBER_PROVIDERS, ENHANCER_PROVIDERS,
    register_transcriber, register_enhancer,
    get_transcriber, get_enhancer,
)

from core.transcription.providers.openai_provider import OpenAITranscriber, OpenAIEnhancer
from core.transcription.providers.anthropic_provider import AnthropicEnhancer
from core.transcription.providers.google_provider import GoogleTranscriber, GoogleEnhancer
from core.transcription.providers.groq_provider import GroqTranscriber, GroqEnhancer

# provider_id → (transcriber_class 或 None, enhancer_class 或 None)
_CLASS_MAP = {
    'openai':    (OpenAITranscriber, OpenAIEnhancer),
    'anthropic': (None,              AnthropicEnhancer),
    'google':    (GoogleTranscriber, GoogleEnhancer),
    'groq':      (GroqTranscriber,   GroqEnhancer),
}


def _load_from_json():
    data = resources.providers().get('providers', {})
    for pid, meta in data.items():
        tcls, ecls = _CLASS_MAP.get(pid, (None, None))
        display = meta.get('display_name', pid)
        env = meta.get('api_key_env', '')
        url = meta.get('api_key_help_url', '')
        t_models = [{'id': m['id'], 'name': m.get('name', m['id'])}
                    for m in meta.get('transcribe_models', [])]
        e_models = [{'id': m['id'], 'name': m.get('name', m['id'])}
                    for m in meta.get('enhance_models', [])]
        if tcls and t_models:
            register_transcriber(pid, display, t_models, tcls, env, url)
        if ecls and e_models:
            register_enhancer(pid, display, e_models, ecls, env, url)


_load_from_json()

__all__ = [
    'TranscriberBase', 'EnhancerBase',
    'TRANSCRIBER_PROVIDERS', 'ENHANCER_PROVIDERS',
    'get_transcriber', 'get_enhancer',
]
