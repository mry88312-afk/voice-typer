"""Claude AI 潤色模組 — 回傳含 token usage 的字典"""
from anthropic import Anthropic


class Enhancer:
    def __init__(self, api_key, prompt=None, model='claude-haiku-4-5-20251001'):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.prompt = prompt or (
            "請將以下口語化的文字整理為通順的書面語，"
            "保持原意，不要添加額外內容，直接輸出整理後的文字："
        )

    def enhance(self, text):
        """回傳 dict: {text, input_tokens, output_tokens, model}"""
        if not text or not text.strip():
            return {
                'text': text,
                'input_tokens': 0,
                'output_tokens': 0,
                'model': self.model,
            }

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    'role': 'user',
                    'content': f"{self.prompt}\n\n{text}",
                }],
            )
            return {
                'text': response.content[0].text.strip(),
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'model': self.model,
            }
        except Exception as e:
            print(f"⚠️  AI 潤色失敗，回傳原文: {e}")
            return {
                'text': text,
                'input_tokens': 0,
                'output_tokens': 0,
                'model': self.model,
            }
