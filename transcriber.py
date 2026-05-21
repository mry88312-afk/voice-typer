"""Whisper API 轉錄模組 — 回傳含音訊時長的字典，用於 usage 統計"""
import os
import soundfile as sf
from openai import OpenAI


class Transcriber:
    def __init__(self, api_key, language='auto', prompt=None, model='whisper-1'):
        self.client = OpenAI(api_key=api_key)
        self.language = language
        self.prompt = prompt or ''
        self.model = model

    def transcribe(self, audio_file_path):
        """回傳 dict: {text, duration_seconds, model}"""
        try:
            # 先計算音訊時長 (用於 usage 計費)
            try:
                info = sf.info(audio_file_path)
                duration_seconds = info.frames / info.samplerate
            except Exception:
                duration_seconds = 0.0

            with open(audio_file_path, 'rb') as audio:
                params = {
                    'model': self.model,
                    'file': audio,
                }
                if self.language and self.language != 'auto':
                    params['language'] = self.language
                if self.prompt:
                    params['prompt'] = self.prompt

                response = self.client.audio.transcriptions.create(**params)
                return {
                    'text': response.text,
                    'duration_seconds': duration_seconds,
                    'model': self.model,
                }
        finally:
            try:
                os.unlink(audio_file_path)
            except OSError:
                pass
