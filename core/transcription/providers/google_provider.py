"""Google Gemini — 多模態音訊轉錄 + 潤色 (會議聲紋分離用)"""
import os
import soundfile as sf
from google import genai
from google.genai import types

from core.transcription.providers.base import TranscriberBase, EnhancerBase


class GoogleTranscriber(TranscriberBase):
    provider_id = 'google'
    model = 'gemini-2.5-flash'
    api_key_env = 'GOOGLE_API_KEY'

    def transcribe(self, audio_file_path):
        client = genai.Client(api_key=self.api_key)
        try:
            duration_seconds = 0.0
            try:
                info = sf.info(audio_file_path)
                duration_seconds = info.frames / info.samplerate
            except Exception:
                pass
            with open(audio_file_path, 'rb') as f:
                audio_bytes = f.read()
            instruction = '請將以下音訊轉成文字，使用繁體中文輸出，加入適當的標點符號。'
            if self.prompt:
                instruction += f' 提示：{self.prompt}'
            response = client.models.generate_content(
                model=self.model,
                contents=[instruction,
                          types.Part.from_bytes(data=audio_bytes, mime_type='audio/wav')],
            )
            usage = getattr(response, 'usage_metadata', None)
            return {'text': response.text or '', 'duration_seconds': duration_seconds,
                    'model': self.model, 'provider': self.provider_id,
                    'input_tokens': getattr(usage, 'prompt_token_count', 0) if usage else 0,
                    'output_tokens': getattr(usage, 'candidates_token_count', 0) if usage else 0}
        finally:
            try:
                os.unlink(audio_file_path)
            except OSError:
                pass


class GoogleEnhancer(EnhancerBase):
    provider_id = 'google'
    model = 'gemini-2.5-flash'
    api_key_env = 'GOOGLE_API_KEY'

    def enhance(self, text):
        if not text or not text.strip():
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
        client = genai.Client(api_key=self.api_key)
        try:
            response = client.models.generate_content(
                model=self.model, contents=f"{self.prompt}\n\n{text}")
            usage = getattr(response, 'usage_metadata', None)
            return {'text': (response.text or '').strip(),
                    'input_tokens': getattr(usage, 'prompt_token_count', 0) if usage else 0,
                    'output_tokens': getattr(usage, 'candidates_token_count', 0) if usage else 0,
                    'model': self.model, 'provider': self.provider_id}
        except Exception as e:
            print(f"Google enhancer failed: {e}")
            return {'text': text, 'input_tokens': 0, 'output_tokens': 0,
                    'model': self.model, 'provider': self.provider_id}
