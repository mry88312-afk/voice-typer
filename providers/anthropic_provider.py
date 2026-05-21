"""Anthropic provider — Claude Haiku / Sonnet / Opus"""
from anthropic import Anthropic

from providers.base import EnhancerBase, register_enhancer


class AnthropicEnhancer(EnhancerBase):
    provider_id = 'anthropic'
    model = 'claude-haiku-4-5-20251001'
    api_key_env = 'ANTHROPIC_API_KEY'

    def enhance(self, text):
        if not text or not text.strip():
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
        client = Anthropic(api_key=self.api_key)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': f"{self.prompt}\n\n{text}"}],
            )
            return {
                'text': response.content[0].text.strip(),
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'model': self.model,
                'provider': self.provider_id,
            }
        except Exception as e:
            print(f"Anthropic enhancer failed: {e}")
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}


register_enhancer(
    'anthropic',
    'Anthropic Claude',
    models=[
        {'id': 'claude-haiku-4-5-20251001', 'name': 'Claude Haiku 4.5 (便宜、快)'},
        {'id': 'claude-sonnet-4-6', 'name': 'Claude Sonnet 4.6 (聰明)'},
        {'id': 'claude-opus-4-7', 'name': 'Claude Opus 4.7 (最聰明、貴)'},
    ],
    cls=AnthropicEnhancer,
    api_key_env='ANTHROPIC_API_KEY',
    api_key_help_url='https://console.anthropic.com/keys',
)
