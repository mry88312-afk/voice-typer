"""OpenAI — Whisper 轉錄 + GPT 潤色"""
import os
import soundfile as sf
from openai import OpenAI

from core.transcription.providers.base import TranscriberBase, EnhancerBase


class OpenAITranscriber(TranscriberBase):
    provider_id = 'openai'
    model = 'whisper-1'
    api_key_env = 'OPENAI_API_KEY'

    def transcribe(self, audio_file_path):
        client = OpenAI(api_key=self.api_key)
        try:
            duration_seconds = 0.0
            try:
                info = sf.info(audio_file_path)
                duration_seconds = info.frames / info.samplerate
            except Exception:
                pass
            with open(audio_file_path, 'rb') as audio:
                params = {'model': self.model, 'file': audio}
                if self.language and self.language != 'auto':
                    params['language'] = self.language
                if self.prompt:
                    params['prompt'] = self.prompt
                response = client.audio.transcriptions.create(**params)
                return {'text': response.text, 'duration_seconds': duration_seconds,
                        'model': self.model, 'provider': self.provider_id}
        finally:
            try:
                os.unlink(audio_file_path)
            except OSError:
                pass


class OpenAIEnhancer(EnhancerBase):
    provider_id = 'openai'
    model = 'gpt-4o-mini'
    api_key_env = 'OPENAI_API_KEY'

    def enhance(self, text):
        if not text or not text.strip():
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
        client = OpenAI(api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': f"{self.prompt}\n\n{text}"}],
                temperature=0.3,
            )
            return {'text': response.choices[0].message.content.strip(),
                    'input_tokens': response.usage.prompt_tokens,
                    'output_tokens': response.usage.completion_tokens,
                    'model': self.model, 'provider': self.provider_id}
        except Exception as e:
            print(f"OpenAI enhancer failed: {e}")
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
