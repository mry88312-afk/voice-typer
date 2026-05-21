"""Groq provider — Whisper Large V3 turbo (極快 + 便宜) + Llama"""
import os
import soundfile as sf
from groq import Groq

from providers.base import (
    TranscriberBase, EnhancerBase,
    register_transcriber, register_enhancer,
)


class GroqTranscriber(TranscriberBase):
    provider_id = 'groq'
    model = 'whisper-large-v3-turbo'
    api_key_env = 'GROQ_API_KEY'

    def transcribe(self, audio_file_path):
        client = Groq(api_key=self.api_key)
        try:
            duration_seconds = 0.0
            try:
                info = sf.info(audio_file_path)
                duration_seconds = info.frames / info.samplerate
            except Exception:
                pass

            with open(audio_file_path, 'rb') as audio:
                params = {
                    'model': self.model,
                    'file': (os.path.basename(audio_file_path), audio.read()),
                    'response_format': 'verbose_json',
                }
                if self.language and self.language != 'auto':
                    params['language'] = self.language
                if self.prompt:
                    params['prompt'] = self.prompt
                response = client.audio.transcriptions.create(**params)
                return {
                    'text': getattr(response, 'text', '') or '',
                    'duration_seconds': duration_seconds,
                    'model': self.model,
                    'provider': self.provider_id,
                }
        finally:
            try:
                os.unlink(audio_file_path)
            except OSError:
                pass


class GroqEnhancer(EnhancerBase):
    provider_id = 'groq'
    model = 'llama-3.3-70b-versatile'
    api_key_env = 'GROQ_API_KEY'

    def enhance(self, text):
        if not text or not text.strip():
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
        client = Groq(api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': f"{self.prompt}\n\n{text}"}],
                temperature=0.3,
            )
            return {
                'text': response.choices[0].message.content.strip(),
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'model': self.model,
                'provider': self.provider_id,
            }
        except Exception as e:
            print(f"Groq enhancer failed: {e}")
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}


register_transcriber(
    'groq',
    'Groq (超快)',
    models=[
        {'id': 'whisper-large-v3-turbo', 'name': 'Whisper Large v3 Turbo (最快)'},
        {'id': 'whisper-large-v3', 'name': 'Whisper Large v3 (準)'},
    ],
    cls=GroqTranscriber,
    api_key_env='GROQ_API_KEY',
    api_key_help_url='https://console.groq.com/keys',
)

register_enhancer(
    'groq',
    'Groq (Llama)',
    models=[
        {'id': 'llama-3.3-70b-versatile', 'name': 'Llama 3.3 70B (聰明、超快)'},
        {'id': 'llama-3.1-8b-instant', 'name': 'Llama 3.1 8B (最快)'},
    ],
    cls=GroqEnhancer,
    api_key_env='GROQ_API_KEY',
    api_key_help_url='https://console.groq.com/keys',
)
