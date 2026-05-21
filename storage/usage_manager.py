"""用量 / 費用追蹤 — 多 provider 通用 (本地估算)

紀錄格式：
{
  'ts': 1700000000.0,
  'kind': 'transcribe' | 'enhance',
  'provider': 'openai' | 'anthropic' | 'google' | 'groq',
  'model': 'whisper-1' | 'claude-haiku-4-5-20251001' | ...,
  'audio_seconds': 12.3,        # transcribe by audio (Whisper / Groq)
  'input_tokens': 100,          # token-based (claude, gpt, gemini, llama)
  'output_tokens': 50,
  'cost_usd': 0.0012,
}
"""
import json
import time
from pathlib import Path
from typing import Optional


# ===========================================================
# 費率表 (USD, 2026-05 參考價)
# 結構: PRICING[kind][provider][model] = {...}
# kind: 'transcribe' (語音轉文字) | 'enhance' (文字 → 文字)
# ===========================================================
PRICING = {
    'transcribe': {
        'openai': {
            'whisper-1':              {'per_minute': 0.006},
            'gpt-4o-mini-transcribe': {'per_minute': 0.003},
            'gpt-4o-transcribe':      {'per_minute': 0.006},
        },
        'groq': {
            # Groq 計費非常便宜，按音檔秒數
            'whisper-large-v3':       {'per_minute': 0.00185},   # $0.111/hr
            'whisper-large-v3-turbo': {'per_minute': 0.000667},  # $0.04/hr (極便宜)
        },
        'google': {
            # Gemini 沒有 per-minute 費率，按 token 算 (估算: 每秒約 32 tokens)
            'gemini-2.5-flash':       {
                'tokens_per_audio_second': 32,
                'input_per_mtok': 0.30,
                'output_per_mtok': 2.50,
            },
            'gemini-2.5-pro':         {
                'tokens_per_audio_second': 32,
                'input_per_mtok': 1.25,
                'output_per_mtok': 10.00,
            },
        },
    },
    'enhance': {
        'openai': {
            'gpt-4o-mini':            {'input_per_mtok': 0.15,  'output_per_mtok': 0.60},
            'gpt-4o':                 {'input_per_mtok': 2.50,  'output_per_mtok': 10.00},
            'gpt-4.1-mini':           {'input_per_mtok': 0.40,  'output_per_mtok': 1.60},
        },
        'anthropic': {
            'claude-haiku-4-5-20251001':  {'input_per_mtok': 1.00,  'output_per_mtok': 5.00},
            'claude-sonnet-4-6':          {'input_per_mtok': 3.00,  'output_per_mtok': 15.00},
            'claude-opus-4-7':            {'input_per_mtok': 15.00, 'output_per_mtok': 75.00},
            'claude-3-5-haiku-20241022':  {'input_per_mtok': 0.80,  'output_per_mtok': 4.00},
            'claude-3-5-sonnet-20241022': {'input_per_mtok': 3.00,  'output_per_mtok': 15.00},
        },
        'google': {
            'gemini-2.5-flash':       {'input_per_mtok': 0.30,  'output_per_mtok': 2.50},
            'gemini-2.5-pro':         {'input_per_mtok': 1.25,  'output_per_mtok': 10.00},
        },
        'groq': {
            'llama-3.3-70b-versatile':{'input_per_mtok': 0.59,  'output_per_mtok': 0.79},
            'llama-3.1-8b-instant':   {'input_per_mtok': 0.05,  'output_per_mtok': 0.08},
        },
    },
}


PROVIDER_DISPLAY = {
    'openai': 'OpenAI',
    'anthropic': 'Anthropic Claude',
    'google': 'Google Gemini',
    'groq': 'Groq',
}

PROVIDER_COLORS = {
    'openai':    '#10B981',   # 綠
    'anthropic': '#B179DE',   # 紫
    'google':    '#4285F4',   # 藍
    'groq':      '#FF6B35',   # 橘
}


def calc_transcribe_cost(provider: str, model: str,
                          audio_seconds: float = 0,
                          input_tokens: int = 0,
                          output_tokens: int = 0) -> float:
    """轉錄費用 — Whisper/Groq 用音訊秒數，Gemini 用 token"""
    rate = PRICING['transcribe'].get(provider, {}).get(model)
    if not rate:
        return 0.0
    # Audio-based 計費 (Whisper, Groq)
    if 'per_minute' in rate:
        return (audio_seconds / 60.0) * rate['per_minute']
    # Token-based 計費 (Gemini)
    if 'tokens_per_audio_second' in rate:
        est_input = input_tokens or int(audio_seconds * rate['tokens_per_audio_second'])
        in_cost = est_input * rate['input_per_mtok'] / 1_000_000
        out_cost = output_tokens * rate.get('output_per_mtok', 0) / 1_000_000
        return in_cost + out_cost
    return 0.0


def calc_enhance_cost(provider: str, model: str,
                       input_tokens: int, output_tokens: int) -> float:
    """潤色費用 — 一律 token-based"""
    rate = PRICING['enhance'].get(provider, {}).get(model)
    if not rate:
        return 0.0
    in_cost = input_tokens * rate.get('input_per_mtok', 0) / 1_000_000
    out_cost = output_tokens * rate.get('output_per_mtok', 0) / 1_000_000
    return in_cost + out_cost


# 向後相容 alias
def calc_openai_whisper_cost(audio_seconds: float, model: str = 'whisper-1') -> float:
    return calc_transcribe_cost('openai', model, audio_seconds=audio_seconds)


def calc_anthropic_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    return calc_enhance_cost('anthropic', model, input_tokens, output_tokens)


# ===========================================================
class UsageManager:
    def __init__(self, path: Path):
        self.path = path
        self._records: list[dict] = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self._records = json.load(f)
            except Exception:
                self._records = []
        else:
            self._records = []
        # 老格式 migration: 若有 provider but no kind，根據 provider 推 kind
        for r in self._records:
            if 'kind' not in r:
                if r.get('audio_seconds') and not r.get('input_tokens'):
                    r['kind'] = 'transcribe'
                else:
                    r['kind'] = 'enhance'

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"usage save failed: {e}")

    # ---------- 新 API ----------
    def record_transcribe(self, provider: str, model: str,
                          audio_seconds: float = 0,
                          input_tokens: int = 0, output_tokens: int = 0) -> float:
        cost = calc_transcribe_cost(provider, model, audio_seconds, input_tokens, output_tokens)
        self._records.append({
            'ts': time.time(),
            'kind': 'transcribe',
            'provider': provider,
            'model': model,
            'audio_seconds': round(audio_seconds, 2),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost_usd': round(cost, 6),
        })
        self.save()
        return cost

    def record_enhance(self, provider: str, model: str,
                       input_tokens: int, output_tokens: int) -> float:
        cost = calc_enhance_cost(provider, model, input_tokens, output_tokens)
        self._records.append({
            'ts': time.time(),
            'kind': 'enhance',
            'provider': provider,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost_usd': round(cost, 6),
        })
        self.save()
        return cost

    # 向後相容
    def record_whisper(self, audio_seconds: float, model: str = 'whisper-1') -> float:
        return self.record_transcribe('openai', model, audio_seconds=audio_seconds)

    def record_claude(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return self.record_enhance('anthropic', model, input_tokens, output_tokens)

    # ---------- Queries ----------
    def all(self) -> list[dict]:
        return list(self._records)

    def filter_since(self, since_ts: float, kind: Optional[str] = None,
                      provider: Optional[str] = None) -> list[dict]:
        recs = self._records
        if kind:
            recs = [r for r in recs if r.get('kind') == kind]
        if provider:
            recs = [r for r in recs if r.get('provider') == provider]
        return [r for r in recs if r.get('ts', 0) >= since_ts]

    def summary(self) -> dict:
        """回傳今日/本月/累計，依 kind × provider 細分"""
        now = time.time()
        today_start = self._start_of_today(now)
        month_start = self._start_of_month(now)

        def aggregate(records):
            out = {
                'total': sum(r.get('cost_usd', 0) for r in records),
                'transcribe': {},   # by provider
                'enhance': {},      # by provider
            }
            for r in records:
                kind = r.get('kind', 'enhance')
                provider = r.get('provider', 'unknown')
                model = r.get('model', '')
                bucket = out[kind].setdefault(provider, {
                    'cost': 0, 'count': 0,
                    'audio_seconds': 0,
                    'input_tokens': 0, 'output_tokens': 0,
                    'models': {},
                })
                bucket['cost'] += r.get('cost_usd', 0)
                bucket['count'] += 1
                bucket['audio_seconds'] += r.get('audio_seconds', 0)
                bucket['input_tokens'] += r.get('input_tokens', 0)
                bucket['output_tokens'] += r.get('output_tokens', 0)
                m = bucket['models'].setdefault(model, {
                    'cost': 0, 'count': 0,
                    'audio_seconds': 0, 'input_tokens': 0, 'output_tokens': 0,
                })
                m['cost'] += r.get('cost_usd', 0)
                m['count'] += 1
                m['audio_seconds'] += r.get('audio_seconds', 0)
                m['input_tokens'] += r.get('input_tokens', 0)
                m['output_tokens'] += r.get('output_tokens', 0)
            return out

        today_recs = [r for r in self._records if r.get('ts', 0) >= today_start]
        month_recs = [r for r in self._records if r.get('ts', 0) >= month_start]

        return {
            'today': aggregate(today_recs),
            'month': aggregate(month_recs),
            'total': aggregate(self._records),
        }

    def daily_trend(self, days: int = 7) -> list[dict]:
        """每天的 transcribe / enhance 細分"""
        import datetime
        now = time.time()
        today_midnight = self._start_of_today(now)
        days_data = []
        for i in range(days - 1, -1, -1):
            day_start = today_midnight - i * 86400
            day_end = day_start + 86400
            day_recs = [r for r in self._records
                        if day_start <= r.get('ts', 0) < day_end]
            d = datetime.datetime.fromtimestamp(day_start)
            transcribe_cost = sum(r.get('cost_usd', 0) for r in day_recs if r.get('kind') == 'transcribe')
            enhance_cost = sum(r.get('cost_usd', 0) for r in day_recs if r.get('kind') == 'enhance')
            days_data.append({
                'date': d.strftime('%m/%d'),
                'transcribe': transcribe_cost,
                'enhance': enhance_cost,
                'total': transcribe_cost + enhance_cost,
            })
        return days_data

    @staticmethod
    def _start_of_today(now: float) -> float:
        import datetime
        d = datetime.datetime.fromtimestamp(now)
        return datetime.datetime(d.year, d.month, d.day).timestamp()

    @staticmethod
    def _start_of_month(now: float) -> float:
        import datetime
        d = datetime.datetime.fromtimestamp(now)
        return datetime.datetime(d.year, d.month, 1).timestamp()

    def clear(self):
        self._records = []
        self.save()

    def export_csv(self, csv_path: Path):
        import csv, datetime
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Kind', 'Provider', 'Model',
                'Audio Seconds', 'Input Tokens', 'Output Tokens',
                'Cost (USD)',
            ])
            for r in self._records:
                writer.writerow([
                    datetime.datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S'),
                    r.get('kind', ''),
                    r.get('provider', ''),
                    r.get('model', ''),
                    r.get('audio_seconds', ''),
                    r.get('input_tokens', ''),
                    r.get('output_tokens', ''),
                    r.get('cost_usd', 0),
                ])
